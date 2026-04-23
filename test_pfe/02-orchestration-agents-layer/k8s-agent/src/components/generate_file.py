"""Generate Kubernetes manifests with secure env var references and LLM support."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import yaml

from ..config import K8S_CONFIG, LLM_CONFIG
from ..models.types import KubernetesManifests, RepositoryContext, UserRequest

logger = logging.getLogger(__name__)


class GenerateFile:
    def __init__(self):
        self.llm_client = None
        self._llm_init_error: Optional[str] = None
        self._init_llm()

    def _init_llm(self):
        if not LLM_CONFIG.get("enabled"):
            logger.info("LLM generation disabled")
            return
        try:
            from src.components.llm_client import LLMClient
            self.llm_client = LLMClient()
            logger.info(f"LLM client initialized: {self.llm_client.model}")
        except Exception as e:
            self._llm_init_error = str(e)
            logger.warning(f"LLM init failed: {e}, using template-only")

    def generate(
        self,
        request: UserRequest,
        context: RepositoryContext,
        intent: Dict[str, Any],
        rag_hints: Dict[str, Any] | None = None,
        use_llm: bool = None,
    ) -> KubernetesManifests:
        use_llm = use_llm if use_llm is not None else (LLM_CONFIG.get("enabled") and self.llm_client is not None)

        app_name = self._normalize_name(intent.get("app_name") or self._derive_app_name(context.repository_path))
        namespace = self._normalize_name(intent.get("namespace") or app_name)
        image = str(intent.get("image") or context.image_name or f"{app_name}:latest")
        replicas = max(1, int(intent.get("replicas") or K8S_CONFIG["default_replicas"]))

        host = intent.get("host") or f"{app_name}{K8S_CONFIG['default_host_suffix']}"
        service_port = int(context.service_port or K8S_CONFIG["default_service_port"])
        container_port = int(context.container_port or K8S_CONFIG["default_container_port"])

        resolved_service_type = self._resolve_service_type(intent, rag_hints)

        config_env = dict(intent.get("config_env") or {})
        secret_env = dict(intent.get("secret_env") or {})

        if not config_env:
            config_env = {"APP_ENV": "development"}
        if not secret_env:
            secret_env = {"APP_SECRET": "replace-me"}

        if use_llm and self.llm_client:
            try:
                logger.info(f"Generating manifests with LLM for app: {app_name}")
                llm_result = self.llm_client.generate_manifests(
                    request.text,
                    {"app_name": app_name, "namespace": namespace, "image": image, "replicas": replicas, "host": host},
                    rag_hints,
                )
                raw_yaml = llm_result.get("raw_yaml") or ""
                if raw_yaml.strip():
                    manifests = self._parse_yaml_output(raw_yaml, app_name, namespace, image, replicas, host, service_port, container_port, resolved_service_type)
                    if manifests:
                        manifests.metadata["generator"] = "llm"
                        manifests.metadata["llm_model"] = self.llm_client.model
                        return manifests
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}, falling back to template")

        logger.info(f"Generating template manifests for app: {app_name}")
        return self._generate_template(
            app_name, namespace, image, replicas, host, service_port,
            container_port, resolved_service_type, config_env, secret_env, rag_hints
        )

    def _generate_template(
        self, app_name: str, namespace: str, image: str, replicas: int,
        host: str, service_port: int, container_port: int, service_type: str,
        config_env: dict, secret_env: dict, rag_hints: Optional[dict]
    ) -> KubernetesManifests:
        namespace_doc = {
            "apiVersion": "v1", "kind": "Namespace",
            "metadata": {"name": namespace},
        }

        configmap_doc = {
            "apiVersion": "v1", "kind": "ConfigMap",
            "metadata": {"name": f"{app_name}-config", "namespace": namespace},
            "data": {k: str(v) for k, v in config_env.items()},
        }

        secret_doc = {
            "apiVersion": "v1", "kind": "Secret",
            "metadata": {"name": f"{app_name}-secret", "namespace": namespace},
            "type": "Opaque",
            "stringData": {k: str(v) for k, v in secret_env.items()},
        }

        env_entries = []
        for key in config_env.keys():
            env_entries.append({"name": key, "valueFrom": {"configMapKeyRef": {"name": f"{app_name}-config", "key": key}}})
        for key in secret_env.keys():
            env_entries.append({"name": key, "valueFrom": {"secretKeyRef": {"name": f"{app_name}-secret", "key": key}}})

        resource_defaults = K8S_CONFIG["resource_defaults"]
        deployment_doc = {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": app_name, "namespace": namespace},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": app_name}},
                "template": {
                    "metadata": {"labels": {"app": app_name}},
                    "spec": {
                        "containers": [{
                            "name": app_name,
                            "image": image,
                            "ports": [{"containerPort": container_port}],
                            "env": env_entries,
                            "resources": resource_defaults,
                        }]
                    }
                },
            },
        }

        service_doc = {
            "apiVersion": "v1", "kind": "Service",
            "metadata": {"name": app_name, "namespace": namespace},
            "spec": {
                "type": service_type,
                "selector": {"app": app_name},
                "ports": [{"port": service_port, "targetPort": container_port}],
            },
        }

        ingress_rule = {
            "host": host,
            "http": {
                "paths": [{
                    "path": "/",
                    "pathType": "Prefix",
                    "backend": {
                        "service": {
                            "name": app_name,
                            "port": {"number": service_port}
                        }
                    }
                }]
            }
        }
        ingress_doc = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {"name": app_name, "namespace": namespace},
            "spec": {"rules": [ingress_rule]},
        }

        hpa_cfg = K8S_CONFIG["hpa"]
        hpa_metric = {
            "type": "Resource",
            "resource": {
                "name": "cpu",
                "target": {
                    "type": "Utilization",
                    "averageUtilization": hpa_cfg["target_cpu_utilization"]
                }
            }
        }
        hpa_doc = {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": f"{app_name}-hpa", "namespace": namespace},
            "spec": {
                "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": app_name},
                "minReplicas": hpa_cfg["min_replicas"],
                "maxReplicas": hpa_cfg["max_replicas"],
                "metrics": [hpa_metric],
            },
        }

        manifests = KubernetesManifests(
            namespace_yaml=self._to_yaml(namespace_doc),
            configmap_yaml=self._to_yaml(configmap_doc),
            secret_yaml=self._to_yaml(secret_doc),
            deployment_yaml=self._to_yaml(deployment_doc),
            service_yaml=self._to_yaml(service_doc),
            ingress_yaml=self._to_yaml(ingress_doc),
            hpa_yaml=self._to_yaml(hpa_doc),
            namespace=namespace,
            app_name=app_name,
            image=image,
            replicas=replicas,
            metadata={
                "host": host,
                "service_port": service_port,
                "container_port": container_port,
                "ingress_class": K8S_CONFIG["default_ingress_class"],
                "service_type": service_type,
                "generator": "template",
                "rag_hints": rag_hints or {},
            },
        )
        manifests.files = {
            "namespace.yaml": manifests.namespace_yaml,
            "configmap.yaml": manifests.configmap_yaml,
            "secret.yaml": manifests.secret_yaml,
            "deployment.yaml": manifests.deployment_yaml,
            "service.yaml": manifests.service_yaml,
            "ingress.yaml": manifests.ingress_yaml,
            "hpa.yaml": manifests.hpa_yaml,
        }
        return manifests

    def _resolve_service_type(self, intent: dict, rag_hints: Optional[dict]) -> str:
        if intent.get("service_type"):
            return intent["service_type"]
        if rag_hints and rag_hints.get("service_type"):
            return rag_hints["service_type"]
        return "ClusterIP"

    def _normalize_name(self, name: str) -> str:
        import re
        return re.sub(r"[^a-z0-9-]", "-", (name or "app").lower().strip("-"))

    def _derive_app_name(self, repo_path: str) -> str:
        p = repo_path or "app"
        return p.rstrip("/\\").split("/")[-1].split("\\")[-1] or "app"

    def _to_yaml(self, doc: dict) -> str:
        return yaml.dump(doc, default_flow_style=False, sort_keys=False)

    def _parse_yaml_output(self, raw_yaml: str, app_name: str, namespace: str, image: str, replicas: int, host: str, service_port: int, container_port: int, service_type: str) -> Optional[KubernetesManifests]:
        return yaml.dump(doc, default_flow_style=False, sort_keys=False)

    def _parse_yaml_output(self, raw_yaml: str, app_name: str, namespace: str, image: str, replicas: int, host: str, service_port: int, container_port: int, service_type: str) -> Optional[KubernetesManifests]:
        try:
            docs = list(yaml.safe_load_all(raw_yaml))
        except Exception as e:
            logger.warning(f"Failed to parse LLM YAML: {e}")
            return None

        namespace_doc = self._find_doc(docs, "Namespace")
        configmap_doc = self._find_doc(docs, "ConfigMap")
        secret_doc = self._find_doc(docs, "Secret")
        deployment_doc = self._find_doc(docs, "Deployment")
        service_doc = self._find_doc(docs, "Service")
        ingress_doc = self._find_doc(docs, "Ingress")
        hpa_doc = self._find_doc(docs, "HorizontalPodAutoscaler")

        manifests = KubernetesManifests(
            namespace_yaml=self._to_yaml(namespace_doc) if namespace_doc else "",
            configmap_yaml=self._to_yaml(configmap_doc) if configmap_doc else "",
            secret_yaml=self._to_yaml(secret_doc) if secret_doc else "",
            deployment_yaml=self._to_yaml(deployment_doc) if deployment_doc else "",
            service_yaml=self._to_yaml(service_doc) if service_doc else "",
            ingress_yaml=self._to_yaml(ingress_doc) if ingress_doc else "",
            hpa_yaml=self._to_yaml(hpa_doc) if hpa_doc else "",
            namespace=namespace,
            app_name=app_name,
            image=image,
            replicas=replicas,
            metadata={"host": host, "service_port": service_port, "container_port": container_port},
        )
        manifests.files = {
            "namespace.yaml": manifests.namespace_yaml,
            "configmap.yaml": manifests.configmap_yaml,
            "secret.yaml": manifests.secret_yaml,
            "deployment.yaml": manifests.deployment_yaml,
            "service.yaml": manifests.service_yaml,
            "ingress.yaml": manifests.ingress_yaml,
            "hpa.yaml": manifests.hpa_yaml,
        }
        return manifests

    def _find_doc(self, docs: list, kind: str) -> Optional[dict]:
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") == kind:
                return doc
        return None
"""Generate Kubernetes manifests with secure env var references."""

from __future__ import annotations

import re
from typing import Any, Dict

import yaml

from ..config import K8S_CONFIG
from ..models.types import KubernetesManifests, RepositoryContext, UserRequest


class GenerateFile:
    def generate(
        self,
        request: UserRequest,
        context: RepositoryContext,
        intent: Dict[str, Any],
        rag_hints: Dict[str, Any] | None = None,
    ) -> KubernetesManifests:
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

        resource_defaults = K8S_CONFIG["resource_defaults"]

        namespace_doc = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace},
        }

        configmap_doc = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": f"{app_name}-config", "namespace": namespace},
            "data": {k: str(v) for k, v in config_env.items()},
        }

        secret_doc = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": f"{app_name}-secret", "namespace": namespace},
            "type": "Opaque",
            "stringData": {k: str(v) for k, v in secret_env.items()},
        }

        env_entries = []
        for key in config_env.keys():
            env_entries.append(
                {
                    "name": key,
                    "valueFrom": {
                        "configMapKeyRef": {
                            "name": f"{app_name}-config",
                            "key": key,
                        }
                    },
                }
            )
        for key in secret_env.keys():
            env_entries.append(
                {
                    "name": key,
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{app_name}-secret",
                            "key": key,
                        }
                    },
                }
            )

        deployment_doc = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": app_name, "namespace": namespace},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": app_name}},
                "template": {
                    "metadata": {"labels": {"app": app_name}},
                    "spec": {
                        "containers": [
                            {
                                "name": app_name,
                                "image": image,
                                "ports": [{"containerPort": container_port}],
                                "resources": {
                                    "requests": resource_defaults["requests"],
                                    "limits": resource_defaults["limits"],
                                },
                                "env": env_entries,
                            }
                        ]
                    },
                },
            },
        }

        service_doc = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": f"{app_name}-svc", "namespace": namespace},
            "spec": {
                "selector": {"app": app_name},
                "ports": [{"port": service_port, "targetPort": container_port}],
                "type": resolved_service_type,
            },
        }

        ingress_doc = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{app_name}-ingress",
                "namespace": namespace,
                "annotations": {},
            },
            "spec": {
                "ingressClassName": K8S_CONFIG["default_ingress_class"],
                "rules": [
                    {
                        "host": host,
                        "http": {
                            "paths": [
                                {
                                    "path": "/",
                                    "pathType": "Prefix",
                                    "backend": {
                                        "service": {
                                            "name": f"{app_name}-svc",
                                            "port": {"number": service_port},
                                        }
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
        }

        hpa_cfg = K8S_CONFIG["hpa"]
        hpa_doc = {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": f"{app_name}-hpa", "namespace": namespace},
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": app_name,
                },
                "minReplicas": hpa_cfg["min_replicas"],
                "maxReplicas": hpa_cfg["max_replicas"],
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": hpa_cfg["target_cpu_utilization"],
                            },
                        },
                    },
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "memory",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": hpa_cfg["target_memory_utilization"],
                            },
                        },
                    },
                ],
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
                "service_type": resolved_service_type,
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

    def _to_yaml(self, content: Dict[str, Any]) -> str:
        return yaml.safe_dump(content, sort_keys=False)

    def _derive_app_name(self, repository_path: str) -> str:
        raw = repository_path.rstrip("/\\").split("/")[-1].split("\\")[-1]
        return self._normalize_name(raw or "app")

    def _normalize_name(self, value: str) -> str:
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9-]", "-", value)
        value = re.sub(r"-+", "-", value).strip("-")
        return value or "app"

    def _resolve_service_type(self, intent: Dict[str, Any], rag_hints: Dict[str, Any] | None) -> str:
        allowed = {"ClusterIP", "NodePort", "LoadBalancer"}

        raw_intent_type = str(intent.get("service_type") or "").strip()
        if raw_intent_type:
            normalized = raw_intent_type.lower()
            mapping = {
                "clusterip": "ClusterIP",
                "nodeport": "NodePort",
                "loadbalancer": "LoadBalancer",
            }
            if normalized in mapping:
                return mapping[normalized]

        hint_type = str((rag_hints or {}).get("service_type") or "").strip()
        if hint_type in allowed:
            return hint_type

        return "ClusterIP"

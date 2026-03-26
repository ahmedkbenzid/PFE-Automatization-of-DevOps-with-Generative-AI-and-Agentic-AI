from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
import json
import re

class Guardrails:
    def __init__(self, api_key: str, model_name: str="llama-3.1-8b-instant"):
        self.llm = ChatGroq(
            api_key=api_key, 
            model=model_name,
            temperature=0  # Deterministic check
        )

    def validate_input(self, user_prompt: str) -> dict:
        """
        Check if the intent is valid and doesn't violate rules.
        Fast-path: Common DevOps keywords bypass LLM validation.
        """
        # Fast-path: DevOps keywords → instant approval
        devops_keywords = [
            "github actions", "workflow", "yaml", "yml", "ci/cd", "pipeline",
            "docker", "dockerfile", "container", "terraform", "hcl", "iac",
            "kubernetes", "k8s", "helm", "aws", "azure", "gcp",
            "jenkins", "gitlab", "sonarqube", "maven", "gradle", "npm",
            "build", "test", "deploy", "ansible", "prometheus", "grafana",
            "nginx", "apache", "linux", "git", "github", "devops"
        ]

        prompt_lower = user_prompt.lower()
        if any(keyword in prompt_lower for keyword in devops_keywords):
            return {"is_allowed": True, "reason": "DevOps keyword detected (fast-path)"}

        # Slow-path: Use LLM for ambiguous requests
        guardrail_prompt = PromptTemplate.from_template(
            "You are a security guardrail for a DevOps automation platform.\n"
            "Your job is to ALLOW legitimate DevOps requests and BLOCK only truly harmful ones.\n\n"
            "ALLOWED requests (approve these):\n"
            "- Requests for Terraform scripts, Dockerfiles, CI/CD pipelines, Kubernetes manifests\n"
            "- Infrastructure provisioning (EC2, S3, VPC, databases, etc.)\n"
            "- Container configuration and orchestration\n"
            "- Monitoring and observability setup\n"
            "- General DevOps questions and best practices\n\n"
            "BLOCKED requests (only block these):\n"
            "- Requests for malware, hacking tools, or exploits\n"
            "- Requests to harm systems or steal data\n"
            "- Content completely unrelated to DevOps/IT\n\n"
            "Input: {user_prompt}\n"
            "Return JSON: {{'is_allowed': boolean, 'reason': 'brief explanation'}}"
        )

        chain = guardrail_prompt | self.llm

        try:
            response = chain.invoke({"user_prompt": user_prompt})
            return self._parse_guardrail_json(response.content)
        except Exception as e:
            return {"is_allowed": False, "reason": f"Guardrail evaluation error: {str(e)}"}

    def _parse_guardrail_json(self, content: str) -> dict:
        cleaned = (content or "").strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "is_allowed" in parsed and "reason" in parsed:
                return parsed
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            candidate = match.group(0)
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "is_allowed" in parsed and "reason" in parsed:
                    return parsed
            except Exception:
                pass

        raise ValueError("Could not parse guardrail JSON response")

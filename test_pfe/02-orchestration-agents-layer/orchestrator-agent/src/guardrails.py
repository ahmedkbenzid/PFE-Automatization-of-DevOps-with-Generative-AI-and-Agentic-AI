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
        """
        guardrail_prompt = PromptTemplate.from_template(
            "You are a security guardrail for a DevOps automation platform.\n"
            "Your job is to ALLOW legitimate DevOps requests and BLOCK only truly harmful ones.\n\n"
            "ALLOWED requests (approve these):\n"
            "- Requests for Terraform scripts, Dockerfiles, CI/CD pipelines, Kubernetes manifests\n"
            "- Infrastructure provisioning (EC2, S3, VPC, databases, etc.)\n"
            "- Container configuration and orchestration\n"
            "- Monitoring and observability setup\n"
            "- General DevOps questions and best practices\n"
            "- Requests mentioning 'script', 'template', 'configuration', 'manifest'\n\n"
            "BLOCKED requests (only block these):\n"
            "- Requests for malware, hacking tools, or exploits\n"
            "- Requests to harm systems or steal data\n"
            "- Content completely unrelated to DevOps/IT\n\n"
            "Input to analyze: {user_prompt}\n\n"
            "If the request is about DevOps, infrastructure, or automation - ALLOW it.\n"
            "Return JSON ONLY with this schema:\n"
            '{{"is_allowed": boolean, "reason": "brief explanation"}}'
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

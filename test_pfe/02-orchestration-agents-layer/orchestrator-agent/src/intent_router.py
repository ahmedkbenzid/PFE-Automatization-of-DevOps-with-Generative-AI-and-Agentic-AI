import json
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from pydantic import SecretStr

class IntentRouter:
    def __init__(self, api_key: str, model_name: str="llama-3.1-8b-instant"):
        self.llm = ChatGroq(
            api_key=SecretStr(api_key), 
            model=model_name,
            temperature=0
        )

    def route(self, user_prompt: str) -> dict:
        """
        Determine which specialized agents should handle the request.
        """
        router_prompt = PromptTemplate.from_template(
            "You are the intelligent intent router for a DevOps multi-agent system.\n"
            "Analyze the user request and determine which agents need to be invoked to fulfill it.\n\n"
            "CRITICAL RULE: ONLY select agents for artifacts the user EXPLICITLY requested.\n"
            "- Do NOT add agents for 'bonus' artifacts the user did not ask for.\n"
            "- If user asks for 'GitHub Actions workflow', select ONLY cicd-agent (not docker-agent).\n"
            "- If user asks for 'Dockerfile', select ONLY docker-agent (not cicd-agent).\n"
            "- Only select multiple agents if the user EXPLICITLY asks for multiple artifact types.\n\n"
            "Available Agents:\n"
            "- cicd-agent: ONLY for GitHub Actions, Jenkins, CI/CD pipelines when explicitly requested.\n"
            "- docker-agent: ONLY for Dockerfiles, Docker Compose when explicitly requested.\n"
            "- k8s-agent: ONLY for Kubernetes manifests, Helm charts when explicitly requested.\n"
            "- iac-agent: ONLY for Terraform, Ansible, infrastructure provisioning when explicitly requested.\n"
            "- monitoring-agent: ONLY for Grafana, Prometheus, observability when explicitly requested.\n"
            "- general-assistant: For generic questions or non-actionable DevOps advice.\n\n"
            "Request: {user_prompt}\n\n"
            "Respond ONLY with a JSON object fitting this structure (do not include markdown block formatting):\n"
            '{{\n'
            '  "primary_agent": "name_of_main_agent",\n'
            '  "secondary_agents": [],\n'
            '  "reasoning": "Brief explanation of why these agents were selected"\n'
            '}}\n\n'
            "IMPORTANT: secondary_agents should be empty [] unless the user explicitly asked for multiple artifact types."
        )
        
        chain = router_prompt | self.llm
        
        try:
            response = chain.invoke({"user_prompt": user_prompt})
            
            # Clean up the output in case the LLM wrapped it in markdown code blocks
            raw_content = response.content
            if isinstance(raw_content, str):
                content = raw_content.strip()
            elif isinstance(raw_content, list):
                content = "".join(
                    part if isinstance(part, str) else str(part.get("text", ""))
                    for part in raw_content
                ).strip()
            else:
                content = str(raw_content).strip()

            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
                
            return json.loads(content.strip())
        except Exception as e:
            return {
                "primary_agent": "error", 
                "secondary_agents": [], 
                "reasoning": f"Routing failed: {str(e)}"
            }

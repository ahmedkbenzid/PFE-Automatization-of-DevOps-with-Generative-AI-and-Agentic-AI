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
            "Available Agents:\n"
            "- cicd-agent: For GitHub Actions, Jenkins, CI/CD pipelines, testing, linting, building.\n"
            "- docker-agent: For Dockerfiles, multi-stage builds, image optimization, and container security checks.\n"
            "- k8s-agent: For Kubernetes manifests, Helm charts, container orchestration.\n"
            "- iac-agent: For Terraform, Ansible, infrastructure provisioning.\n"
            "- monitoring-agent: For Grafana, Prometheus, observability setup.\n"
            "- general-assistant: For generic questions or non-actionable DevOps advice.\n\n"
            "Request: {user_prompt}\n\n"
            "Respond ONLY with a JSON object fitting this structure (do not include markdown block formatting):\n"
            '{{\n'
            '  "primary_agent": "name_of_main_agent",\n'
            '  "secondary_agents": ["name_of_other_agent1", "name_of_other_agent2"],\n'
            '  "reasoning": "Brief explanation of why these agents were selected"\n'
            '}}'
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

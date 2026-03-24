"""LLM integration with Groq API"""
from typing import Optional
from src.config import Config
from src.models.types import IntentMetadata, RequestType

try:
    from groq import Groq
except ModuleNotFoundError:
    Groq = None

class GroqLLMClient:
    """LLM client using Groq API"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.GROQ_API_KEY
        self.client = Groq(api_key=self.api_key) if Groq is not None else None
        self.model = Config.GROQ_MODEL
        self.fallback_models = [m for m in Config.GROQ_FALLBACK_MODELS if m != self.model]
        self.max_tokens = Config.GROQ_MAX_TOKENS
        self.temperature = Config.GROQ_TEMPERATURE

    def _completion(self, model: str, prompt: str, max_tokens: Optional[int] = None):
        return self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature,
            top_p=0.95,
            stream=False,
        )
        
    def generate_text(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate text using Groq LLM"""
        if self.client is None:
            raise RuntimeError("groq package is not installed. Run: pip install groq")

        try:
            message = self._completion(self.model, prompt, max_tokens=max_tokens)
            return message.choices[0].message.content
        except Exception as e:
            error_text = str(e).lower()
            should_try_fallbacks = "model_decommissioned" in error_text or "decommissioned" in error_text or "not found" in error_text

            if should_try_fallbacks:
                for fallback_model in self.fallback_models:
                    try:
                        message = self._completion(fallback_model, prompt, max_tokens=max_tokens)
                        self.model = fallback_model
                        return message.choices[0].message.content
                    except Exception:
                        continue

            raise Exception(f"Error generating text with Groq: {str(e)}")
    
    def extract_intent(self, user_request: str) -> IntentMetadata:
        """Extract intent from user request"""
        prompt = f"""Analyze the following user request for a CI/CD workflow and extract the intent:

User Request: "{user_request}"

Respond in the following format:
INTENT: [Main intent in 1 sentence]
KEYWORDS: [Comma-separated keywords]
REQUEST_TYPE: [CREATE_WORKFLOW|MIGRATE_WORKFLOW|OPTIMIZE_WORKFLOW|VALIDATE_WORKFLOW]
TOOLS_NEEDED: [Comma-separated tools needed]
CONFIDENCE: [0.0-1.0]
"""
        response = self.generate_text(prompt)
        
        intent_data = self._parse_intent_response(response, user_request)
        return intent_data
    
    def _parse_intent_response(self, response: str, fallback_intent: str = "Create CI/CD workflow") -> IntentMetadata:
        """Parse LLM response into IntentMetadata"""
        lines = response.strip().split('\n')
        intent_dict = {}
        
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                intent_dict[key.strip().lower()] = value.strip()
        
        request_type = RequestType.CREATE_WORKFLOW
        if 'migrate' in intent_dict.get('request_type', '').lower():
            request_type = RequestType.MIGRATE_WORKFLOW
        elif 'optimize' in intent_dict.get('request_type', '').lower():
            request_type = RequestType.OPTIMIZE_WORKFLOW
        elif 'validate' in intent_dict.get('request_type', '').lower():
            request_type = RequestType.VALIDATE_WORKFLOW
        
        keywords = [k.strip() for k in intent_dict.get('keywords', '').split(',') if k.strip()]
        tools = [t.strip() for t in intent_dict.get('tools_needed', '').split(',') if t.strip()]
        
        try:
            confidence = float(intent_dict.get('confidence', '0.5'))
        except ValueError:
            confidence = 0.5
        
        return IntentMetadata(
            intent=intent_dict.get('intent', fallback_intent),
            keywords=keywords,
            request_type=request_type,
            required_tools=tools,
            confidence=confidence
        )
    
    def generate_workflow_yaml(self, prompt: str) -> str:
        """Generate GitHub Actions workflow YAML"""
        expanded_prompt = f"""{prompt}

Generate a complete GitHub Actions workflow in YAML format. The output MUST be valid YAML and include:
1. name
2. on (with appropriate triggers)
3. jobs with at least one job
4. steps in each job
5. Proper indentation

Output ONLY the YAML content, no explanations."""
        
        return self.generate_text(expanded_prompt, max_tokens=3000)
    
    def validate_workflow_logic(self, yaml_content: str, errors: list) -> str:
        """Use LLM to suggest fixes for workflow errors"""
        prompt = f"""Review this GitHub Actions workflow YAML and the validation errors.
Suggest fixes for the errors:

YAML:
{yaml_content}

Validation Errors:
{chr(10).join(errors)}

Provide fixed YAML that addresses these errors."""
        
        return self.generate_text(prompt, max_tokens=3000)

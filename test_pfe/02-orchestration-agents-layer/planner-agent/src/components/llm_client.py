"""
LLM Client for Planner Agent

Handles LLM communication for intelligent planning and intent analysis.
"""

from typing import Optional
from ollama import chat
from groq import Groq

from src.config import PlannerConfig


class PlannerLLMClient:
    """LLM client for planner agent"""
    
    def __init__(self):
        self.config = PlannerConfig()
        llm_config = self.config.get_llm_config()
        
        self.provider = llm_config["provider"]
        self.model = llm_config["model"]
        self.temperature = llm_config["temperature"]
        self.max_tokens = llm_config["max_tokens"]
        
        if self.provider == "groq":
            self.groq_client = Groq(api_key=llm_config["api_key"])
    
    def generate(self, prompt: str) -> str:
        """
        Generate LLM response for planning
        
        Args:
            prompt: Planning prompt
            
        Returns:
            LLM response text
        """
        if self.provider == "groq":
            return self._groq_completion(prompt)
        else:
            return self._ollama_completion(prompt)
    
    def _ollama_completion(self, prompt: str) -> str:
        """Generate completion using Ollama"""
        try:
            response = chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                }
            )
            return response.message.content
        except Exception as e:
            print(f"[Planner LLM] Ollama error: {str(e)}")
            return "{}"
    
    def _groq_completion(self, prompt: str) -> str:
        """Generate completion using Groq"""
        try:
            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Planner LLM] Groq error: {str(e)}")
            return "{}"

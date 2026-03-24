"""Security guardrails for workflow execution"""
from typing import List, Dict, Any
from src.models.types import SecurityAuditResult

class SecurityGuardrails:
    """Enforce security best practices for workflows"""
    
    # Dangerous patterns to check
    DANGEROUS_PATTERNS = [
        'rm -rf /',
        'eval(',
        'exec(',
        'subprocess.call',
        '__import__',
        'os.system',
        'os.popen',
        '::/etc/passwd',
        '/etc/shadow',
    ]
    
    # Restricted actions
    RESTRICTED_ACTIONS = [
        'actions/upload-artifact',  # Can leak secrets
        'actions/download-artifact',  # Should be careful
    ]
    
    # Safe actions whitelist
    SAFE_ACTIONS_PREFIXES = [
        'actions/',
        'docker://',
        'github/',
    ]
    
    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
    
    def audit_workflow(self, parsed_workflow: Dict[str, Any], yaml_content: str) -> SecurityAuditResult:
        """Perform security audit on workflow"""
        risks = []
        unsafe_patterns_found = []
        actions = []
        
        # Check for dangerous patterns in YAML
        pattern_risks = self._check_dangerous_patterns(yaml_content)
        risks.extend(pattern_risks['risks'])
        unsafe_patterns_found.extend(pattern_risks['patterns'])
        
        # Check actions
        action_risks, actions_used = self._audit_actions(parsed_workflow)
        risks.extend(action_risks)
        
        # Check for secret exposure
        secret_risks = self._check_secret_exposure(yaml_content)
        risks.extend(secret_risks)
        
        # Check permissions
        permission_risks = self._check_permissions(parsed_workflow)
        risks.extend(permission_risks)
        
        # Check for external URLs
        url_risks = self._check_external_urls(yaml_content)
        risks.extend(url_risks)
        
        is_safe = len(risks) == 0 if self.strict_mode else len([r for r in risks if r['severity'] == 'critical']) == 0
        
        return SecurityAuditResult(
            is_safe=is_safe,
            risks=risks,
            actions_used=actions_used,
            unsafe_patterns=unsafe_patterns_found,
        )
    
    def _check_dangerous_patterns(self, content: str) -> Dict[str, Any]:
        """Check for dangerous patterns in workflow content"""
        risks = []
        patterns_found = []
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in self.DANGEROUS_PATTERNS:
                if pattern in line:
                    risks.append({
                        'line': i,
                        'pattern': pattern,
                        'severity': 'critical',
                        'description': f'Dangerous pattern found: {pattern}',
                    })
                    patterns_found.append(pattern)
        
        return {'risks': risks, 'patterns': patterns_found}
    
    def _audit_actions(self, workflow: Dict[str, Any]) -> tuple[List[Dict], List[str]]:
        """Audit actions used in workflow"""
        risks = []
        actions_used = []
        
        jobs = workflow.get('jobs', {})
        for job_name, job_config in jobs.items():
            steps = job_config.get('steps', [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                
                uses = step.get('uses', '')
                if uses:
                    actions_used.append(uses)
                    
                    # Check if action is from verified source
                    if not any(uses.startswith(prefix) for prefix in self.SAFE_ACTIONS_PREFIXES):
                        risks.append({
                            'action': uses,
                            'severity': 'warning',
                            'description': f'Action from unverified source: {uses}',
                        })
                    
                    # Check if action needs approval
                    if any(restricted in uses for restricted in self.RESTRICTED_ACTIONS):
                        risks.append({
                            'action': uses,
                            'severity': 'warning',
                            'description': f'Restricted action that needs careful review: {uses}',
                        })
        
        return risks, actions_used
    
    def _check_secret_exposure(self, content: str) -> List[Dict]:
        """Check for potential secret exposure"""
        risks = []
        
        secret_indicators = [
            'password',
            'token',
            'api_key',
            'secret',
            'credentials',
            'private_key',
        ]
        
        if 'echo' in content or 'print' in content:
            for indicator in secret_indicators:
                if indicator in content.lower():
                    risks.append({
                        'indicator': indicator,
                        'severity': 'medium',
                        'description': f'Potential {indicator} exposure in output',
                    })
        
        return risks
    
    def _check_permissions(self, workflow: Dict[str, Any]) -> List[Dict]:
        """Check workflow permissions"""
        risks = []
        
        permissions = workflow.get('permissions', {})
        
        # Default is all permissions, which is risky
        if not permissions:
            risks.append({
                'severity': 'warning',
                'description': 'No explicit permissions defined, defaults to all permissions',
            })
        
        # Check for excessive permissions
        if isinstance(permissions, dict):
            for perm, value in permissions.items():
                if value in ('write', 'admin'):
                    risks.append({
                        'permission': perm,
                        'severity': 'warning',
                        'description': f'Excessive permission granted: {perm}={value}',
                    })
        
        return risks
    
    def _check_external_urls(self, content: str) -> List[Dict]:
        """Check for downloads from external/untrusted URLs"""
        risks = []
        
        import re
        url_pattern = r'https?://[^\s\'">\]}\)]+(?:\.[a-z]{2,})+(?:[/?#].*)?'
        urls = re.findall(url_pattern, content.lower())
        
        # Check for suspicious domains
        suspicious_domains = ['raw.githubusercontent.com', 'bit.ly', 'tinyurl', 'pastebin']
        
        for url in urls:
            for domain in suspicious_domains:
                if domain in url:
                    risks.append({
                        'url': url,
                        'severity': 'warning',
                        'description': f'Potentially unsafe URL from {domain}',
                    })
        
        return risks
    
    def add_security_headers(self, yaml_content: str) -> str:
        """Add security best practice headers to YAML"""
        security_headers = [
            '# Security: Restrict permissions to minimum required',
            'permissions:',
            '  contents: read',
            '',
        ]
        
        return '\n'.join(security_headers) + yaml_content if 'permissions' not in yaml_content else yaml_content

"""
Enhanced chunking strategies for knowledge base content.

Provides intelligent chunking of CI/CD workflows to improve retrieval accuracy
by creating semantically meaningful chunks that align with user prompt patterns.
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class Chunk:
    """A semantic chunk of content."""
    chunk_id: str
    content: str
    chunk_type: str  # 'metadata', 'trigger', 'job', 'step', 'full'
    context: Dict[str, Any]  # Preserved context for understanding
    start_line: int
    end_line: int
    importance_score: float = 1.0


class WorkflowChunker:
    """Intelligent chunking for GitHub Actions workflows."""
    
    def __init__(self, overlap_lines: int = 2, max_chunk_size: int = 500):
        """
        Args:
            overlap_lines: Number of lines to overlap between chunks for context
            max_chunk_size: Maximum characters per chunk
        """
        self.overlap_lines = overlap_lines
        self.max_chunk_size = max_chunk_size
    
    def chunk_workflow(self, content: str, page_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """
        Chunk a workflow into semantically meaningful pieces.
        
        Strategies:
        1. Metadata chunk (name, triggers, environment)
        2. Job-level chunks (each job as a unit)
        3. Step-level chunks for complex jobs
        4. Full content chunk for small workflows
        
        Args:
            content: YAML workflow content
            page_id: Unique identifier for the page
            metadata: Additional metadata about the workflow
            
        Returns:
            List of semantic chunks with preserved context
        """
        chunks = []
        lines = content.split('\n')
        
        # Strategy 1: Extract metadata chunk (high importance for matching)
        metadata_chunk = self._extract_metadata_chunk(content, lines, page_id, metadata)
        if metadata_chunk:
            chunks.append(metadata_chunk)
        
        # Strategy 2: Detect and chunk by jobs
        job_chunks = self._extract_job_chunks(content, lines, page_id, metadata)
        chunks.extend(job_chunks)
        
        # Strategy 3: If workflow is small, include full content chunk
        if len(content) <= self.max_chunk_size:
            chunks.append(Chunk(
                chunk_id=f"{page_id}-full",
                content=content,
                chunk_type="full",
                context={"type": "complete_workflow", **metadata},
                start_line=0,
                end_line=len(lines) - 1,
                importance_score=0.8  # Lower score since it's redundant
            ))
        
        return chunks
    
    def _extract_metadata_chunk(
        self, 
        content: str, 
        lines: List[str], 
        page_id: str, 
        metadata: Dict[str, Any]
    ) -> Optional[Chunk]:
        """Extract workflow metadata (name, on, env, defaults)."""
        metadata_lines = []
        metadata_context = {}
        
        # Extract workflow name
        name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
        if name_match:
            metadata_context['workflow_name'] = name_match.group(1).strip()
            metadata_lines.append(f"name: {name_match.group(1).strip()}")
        
        # Extract triggers (on:)
        trigger_patterns = [
            r'on:\s*\[([^\]]+)\]',  # on: [push, pull_request]
            r'on:\s*(\w+)',          # on: push
            r'on:\s*\n((?:\s+\w+:.*\n?)+)',  # multi-line triggers
        ]
        
        for pattern in trigger_patterns:
            trigger_match = re.search(pattern, content, re.MULTILINE)
            if trigger_match:
                trigger_text = trigger_match.group(1).strip()
                metadata_context['triggers'] = trigger_text
                metadata_lines.append(f"triggers: {trigger_text}")
                break
        
        # Extract environment variables
        env_match = re.search(r'^env:\s*\n((?:\s+\w+:.*\n?)+)', content, re.MULTILINE)
        if env_match:
            env_text = env_match.group(1).strip()
            metadata_context['environment'] = env_text
            metadata_lines.append(f"environment:\n{env_text}")
        
        # Add language and patterns from metadata
        if metadata.get('language'):
            metadata_context['language'] = metadata['language']
            metadata_lines.append(f"language: {metadata['language']}")
        
        if metadata.get('patterns'):
            metadata_context['patterns'] = metadata['patterns']
            metadata_lines.append(f"patterns: {', '.join(metadata['patterns'])}")
        
        if not metadata_lines:
            return None
        
        return Chunk(
            chunk_id=f"{page_id}-metadata",
            content='\n'.join(metadata_lines),
            chunk_type="metadata",
            context=metadata_context,
            start_line=0,
            end_line=min(20, len(lines) - 1),
            importance_score=1.5  # High importance for initial matching
        )
    
    def _extract_job_chunks(
        self, 
        content: str, 
        lines: List[str], 
        page_id: str, 
        metadata: Dict[str, Any]
    ) -> List[Chunk]:
        """Extract individual job chunks."""
        chunks = []
        
        # Find jobs section
        jobs_match = re.search(r'^jobs:\s*\n', content, re.MULTILINE)
        if not jobs_match:
            return chunks
        
        jobs_start = jobs_match.end()
        jobs_content = content[jobs_start:]
        
        # Parse job definitions (looking for top-level job keys)
        # Pattern: job_name: (with proper indentation)
        job_pattern = r'^  (\w[\w-]*):.*?\n(?=^  \w|^[^\s]|\Z)'
        
        job_matches = list(re.finditer(job_pattern, jobs_content, re.MULTILINE | re.DOTALL))
        
        for idx, job_match in enumerate(job_matches):
            job_name = job_match.group(1)
            job_content = job_match.group(0)
            
            # Extract job context
            job_context = {
                'job_name': job_name,
                'language': metadata.get('language'),
                **self._analyze_job_content(job_content)
            }
            
            # Calculate line numbers
            start_idx = jobs_match.start() + job_match.start()
            start_line = content[:start_idx].count('\n')
            end_line = start_line + job_content.count('\n')
            
            # Create job chunk
            chunk_content = f"job: {job_name}\n{job_content}"
            
            # If job is too large, split into step chunks
            if len(chunk_content) > self.max_chunk_size:
                step_chunks = self._extract_step_chunks(
                    job_content, 
                    job_name, 
                    f"{page_id}-job-{idx}", 
                    job_context,
                    start_line
                )
                chunks.extend(step_chunks)
            else:
                chunks.append(Chunk(
                    chunk_id=f"{page_id}-job-{idx}",
                    content=chunk_content,
                    chunk_type="job",
                    context=job_context,
                    start_line=start_line,
                    end_line=end_line,
                    importance_score=1.2  # Jobs are important semantic units
                ))
        
        return chunks
    
    def _analyze_job_content(self, job_content: str) -> Dict[str, Any]:
        """Analyze job content to extract semantic information."""
        analysis = {
            'has_matrix': 'matrix:' in job_content,
            'has_services': 'services:' in job_content,
            'has_container': 'container:' in job_content,
            'actions_used': [],
            'commands_used': [],
        }
        
        # Extract actions (uses:)
        action_pattern = r'uses:\s*([^\s\n]+)'
        actions = re.findall(action_pattern, job_content)
        analysis['actions_used'] = list(set(actions))
        
        # Extract run commands (for technology detection)
        run_pattern = r'run:\s*([^\n]+)'
        runs = re.findall(run_pattern, job_content)
        analysis['commands_used'] = [cmd.strip() for cmd in runs]
        
        # Detect patterns
        patterns = []
        job_lower = job_content.lower()
        if any(test in job_lower for test in ['test', 'pytest', 'jest', 'junit', 'mocha']):
            patterns.append('testing')
        if any(build in job_lower for build in ['build', 'compile', 'mvn', 'gradle', 'npm build']):
            patterns.append('build')
        if 'deploy' in job_lower:
            patterns.append('deploy')
        if 'docker' in job_lower:
            patterns.append('docker')
        if 'sonar' in job_lower:
            patterns.append('code-quality')
        if any(k8s in job_lower for k8s in ['kubernetes', 'kubectl', 'helm']):
            patterns.append('kubernetes')
        
        analysis['patterns'] = patterns
        
        return analysis
    
    def _extract_step_chunks(
        self, 
        job_content: str, 
        job_name: str,
        job_chunk_id: str, 
        job_context: Dict[str, Any],
        job_start_line: int
    ) -> List[Chunk]:
        """Extract individual step chunks from a large job."""
        chunks = []
        
        # Find steps section
        steps_match = re.search(r'steps:\s*\n', job_content)
        if not steps_match:
            return chunks
        
        steps_content = job_content[steps_match.end():]
        
        # Split by step markers (- name: or - uses: or - run:)
        step_pattern = r'(    -\s+(?:name:|uses:|run:).+?)(?=\n    -\s+|\Z)'
        step_matches = list(re.finditer(step_pattern, steps_content, re.DOTALL))
        
        for idx, step_match in enumerate(step_matches):
            step_content = step_match.group(1).strip()
            
            # Skip very small steps
            if len(step_content) < 50:
                continue
            
            # Extract step name or infer from content
            step_name = self._extract_step_name(step_content)
            
            start_idx = steps_match.start() + step_match.start()
            start_line = job_start_line + job_content[:start_idx].count('\n')
            end_line = start_line + step_content.count('\n')
            
            chunks.append(Chunk(
                chunk_id=f"{job_chunk_id}-step-{idx}",
                content=f"job: {job_name}\nstep: {step_name}\n{step_content}",
                chunk_type="step",
                context={
                    **job_context,
                    'step_name': step_name,
                    'step_index': idx
                },
                start_line=start_line,
                end_line=end_line,
                importance_score=1.0
            ))
        
        return chunks
    
    def _extract_step_name(self, step_content: str) -> str:
        """Extract or infer step name."""
        # Try to find explicit name
        name_match = re.search(r'name:\s*(.+)$', step_content, re.MULTILINE)
        if name_match:
            return name_match.group(1).strip()
        
        # Try to find uses action
        uses_match = re.search(r'uses:\s*([^\s@\n]+)', step_content)
        if uses_match:
            return uses_match.group(1).split('/')[-1]
        
        # Try to find run command
        run_match = re.search(r'run:\s*([^\n]+)', step_content)
        if run_match:
            cmd = run_match.group(1).strip()
            return cmd[:50] + ('...' if len(cmd) > 50 else '')
        
        return "unnamed-step"


class EnhancedChunkRetriever:
    """Enhanced retrieval using semantic chunks."""
    
    def __init__(self):
        self.chunker = WorkflowChunker()
    
    def query_with_chunks(
        self, 
        query_text: str, 
        pages: List[Dict[str, Any]], 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query using enhanced chunking strategy.
        
        Args:
            query_text: User query
            pages: List of knowledge pages
            top_k: Number of results to return
            
        Returns:
            List of ranked results with relevant chunks
        """
        query_tokens = self._tokenize(query_text)
        query_context = self._extract_query_context(query_text)
        
        scored_chunks = []
        
        for page in pages:
            # Chunk the page content
            chunks = self.chunker.chunk_workflow(
                content=page.get('content', ''),
                page_id=page.get('page_id', 'unknown'),
                metadata=page.get('metadata', {})
            )
            
            # Score each chunk
            for chunk in chunks:
                score = self._score_chunk(chunk, query_tokens, query_context)
                if score > 0:
                    scored_chunks.append((score, chunk, page))
        
        # Sort by score
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        
        # Build results
        results = []
        seen_pages = set()
        
        for score, chunk, page in scored_chunks[:top_k * 2]:  # Get more candidates
            page_id = page.get('page_id')
            
            # Include best chunk per page
            if page_id not in seen_pages or len(results) < top_k:
                results.append({
                    'score': score,
                    'page_id': page_id,
                    'title': page.get('title'),
                    'source': page.get('source'),
                    'tags': page.get('tags', []),
                    'content': chunk.content,  # Return the relevant chunk
                    'chunk_type': chunk.chunk_type,
                    'chunk_context': chunk.context,
                    'full_content': page.get('content', '')[:2000] if len(results) < 3 else None
                })
                seen_pages.add(page_id)
            
            if len(results) >= top_k:
                break
        
        return results
    
    def _score_chunk(
        self, 
        chunk: Chunk, 
        query_tokens: set, 
        query_context: Dict[str, Any]
    ) -> float:
        """
        Score chunk relevance with context awareness.
        
        Scoring factors:
        1. Token overlap (base score)
        2. Chunk type importance
        3. Context matching (language, patterns, triggers)
        4. Chunk importance score
        """
        chunk_tokens = self._tokenize(chunk.content)
        
        # Base token overlap score
        overlap = len(query_tokens.intersection(chunk_tokens))
        if overlap == 0:
            return 0.0
        
        base_score = overlap
        
        # Apply chunk importance multiplier
        base_score *= chunk.importance_score
        
        # Bonus for context matching
        context_bonus = 0.0
        
        # Language match
        if query_context.get('language') and chunk.context.get('language'):
            if query_context['language'].lower() == chunk.context['language'].lower():
                context_bonus += 2.0
        
        # Pattern match
        query_patterns = set(query_context.get('patterns', []))
        chunk_patterns = set(chunk.context.get('patterns', []))
        pattern_overlap = len(query_patterns.intersection(chunk_patterns))
        context_bonus += pattern_overlap * 1.5
        
        # Trigger match
        if query_context.get('triggers') and chunk.context.get('triggers'):
            query_triggers = query_context['triggers']
            chunk_triggers = chunk.context['triggers'].lower()
            # Check if any query trigger is in the chunk triggers string
            if any(trigger in chunk_triggers for trigger in query_triggers):
                context_bonus += 1.0
        
        # Job name match
        if query_context.get('job_terms'):
            chunk_job = chunk.context.get('job_name', '').lower()
            if any(term in chunk_job for term in query_context['job_terms']):
                context_bonus += 1.5
        
        # Action match (specific GitHub Actions)
        if query_context.get('actions'):
            chunk_actions = [a.lower() for a in chunk.context.get('actions_used', [])]
            for action in query_context['actions']:
                if any(action in ca for ca in chunk_actions):
                    context_bonus += 2.0
        
        return base_score + context_bonus
    
    def _extract_query_context(self, query_text: str) -> Dict[str, Any]:
        """Extract semantic context from query."""
        query_lower = query_text.lower()
        context = {
            'patterns': [],
            'triggers': [],
            'job_terms': [],
            'actions': [],
        }
        
        # Detect language
        languages = {
            'python': ['python', 'pip', 'pytest', 'django', 'flask'],
            'javascript': ['javascript', 'node', 'npm', 'yarn', 'jest', 'react', 'vue'],
            'java': ['java', 'maven', 'mvn', 'gradle', 'spring', 'junit'],
            'go': ['golang', 'go'],
            'rust': ['rust', 'cargo'],
            'ruby': ['ruby', 'gem', 'bundle'],
            'php': ['php', 'composer'],
            'c#': ['c#', 'csharp', 'dotnet', 'nuget'],
        }
        
        for lang, keywords in languages.items():
            if any(keyword in query_lower for keyword in keywords):
                context['language'] = lang.title()
                break
        
        # Detect patterns
        if any(term in query_lower for term in ['test', 'testing', 'pytest', 'jest', 'junit']):
            context['patterns'].append('testing')
        if any(term in query_lower for term in ['build', 'compile', 'compilation']):
            context['patterns'].append('build')
        if 'deploy' in query_lower or 'deployment' in query_lower:
            context['patterns'].append('deploy')
        if 'docker' in query_lower or 'container' in query_lower:
            context['patterns'].append('docker')
        if 'sonar' in query_lower or 'code quality' in query_lower:
            context['patterns'].append('code-quality')
        if any(term in query_lower for term in ['kubernetes', 'k8s', 'helm', 'kubectl']):
            context['patterns'].append('kubernetes')
        
        # Detect triggers
        if 'push' in query_lower:
            context['triggers'].append('push')
        if 'pull request' in query_lower or 'pr' in query_lower:
            context['triggers'].append('pull_request')
        if 'schedule' in query_lower or 'cron' in query_lower:
            context['triggers'].append('schedule')
        
        # Detect job-related terms
        job_keywords = ['ci', 'cd', 'build', 'test', 'deploy', 'lint', 'security']
        context['job_terms'] = [term for term in job_keywords if term in query_lower]
        
        # Detect specific actions
        action_keywords = ['checkout', 'setup-python', 'setup-node', 'setup-java', 'cache', 'upload-artifact']
        context['actions'] = [action for action in action_keywords if action in query_lower]
        
        return context
    
    def _tokenize(self, text: str) -> set:
        """Tokenize text for matching."""
        return set(re.findall(r'[a-zA-Z0-9_\-.]+', text.lower()))

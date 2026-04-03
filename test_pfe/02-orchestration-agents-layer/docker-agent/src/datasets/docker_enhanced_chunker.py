"""
Enhanced chunking strategies for Docker knowledge base content.

Provides intelligent chunking of Dockerfiles and Docker Compose files to improve 
retrieval accuracy by creating semantically meaningful chunks that align with user prompts.
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class DockerChunk:
    """A semantic chunk of Docker content."""
    chunk_id: str
    content: str
    chunk_type: str  # 'metadata', 'base_image', 'stage', 'instruction_group', 'full'
    context: Dict[str, Any]  # Preserved context for understanding
    start_line: int
    end_line: int
    importance_score: float = 1.0


class DockerfileChunker:
    """Intelligent chunking for Dockerfiles."""
    
    def __init__(self, overlap_lines: int = 2, max_chunk_size: int = 500):
        """
        Args:
            overlap_lines: Number of lines to overlap between chunks for context
            max_chunk_size: Maximum characters per chunk
        """
        self.overlap_lines = overlap_lines
        self.max_chunk_size = max_chunk_size
    
    def chunk_dockerfile(self, content: str, page_id: str, metadata: Dict[str, Any]) -> List[DockerChunk]:
        """
        Chunk a Dockerfile into semantically meaningful pieces.
        
        Strategies:
        1. Metadata chunk (base image, stack type, labels)
        2. Stage-level chunks (for multi-stage builds)
        3. Instruction group chunks (related instructions)
        4. Full content chunk for small Dockerfiles
        
        Args:
            content: Dockerfile content
            page_id: Unique identifier for the page
            metadata: Additional metadata about the Dockerfile
            
        Returns:
            List of semantic chunks with preserved context
        """
        chunks = []
        lines = content.split('\n')
        
        # Strategy 1: Extract metadata chunk (high importance for matching)
        metadata_chunk = self._extract_metadata_chunk(content, lines, page_id, metadata)
        if metadata_chunk:
            chunks.append(metadata_chunk)
        
        # Strategy 2: Detect and chunk by stages (multi-stage builds)
        stage_chunks = self._extract_stage_chunks(content, lines, page_id, metadata)
        chunks.extend(stage_chunks)
        
        # Strategy 3: If Dockerfile is small, include full content chunk
        if len(content) <= self.max_chunk_size:
            chunks.append(DockerChunk(
                chunk_id=f"{page_id}-full",
                content=content,
                chunk_type="full",
                context={"type": "complete_dockerfile", **metadata},
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
    ) -> Optional[DockerChunk]:
        """Extract Dockerfile metadata (FROM, LABEL, stack type, etc.)."""
        metadata_lines = []
        metadata_context = {}
        
        # Extract FROM statements (base images)
        from_matches = re.findall(r'^FROM\s+([^\s]+)(?:\s+AS\s+([^\s]+))?', content, re.MULTILINE | re.IGNORECASE)
        if from_matches:
            base_images = []
            stages = []
            for image, stage_name in from_matches:
                base_images.append(image)
                if stage_name:
                    stages.append(stage_name)
            
            metadata_context['base_images'] = base_images
            metadata_context['is_multi_stage'] = len(from_matches) > 1
            if stages:
                metadata_context['stages'] = stages
            
            metadata_lines.append(f"base_images: {', '.join(base_images)}")
            if stages:
                metadata_lines.append(f"stages: {', '.join(stages)}")
        
        # Extract LABELs
        label_matches = re.findall(r'^LABEL\s+(.+)', content, re.MULTILINE | re.IGNORECASE)
        if label_matches:
            labels = [label.strip() for label in label_matches]
            metadata_context['labels'] = labels
            metadata_lines.append(f"labels: {len(labels)} defined")
        
        # Detect stack/language from content
        stack = self._detect_stack(content)
        if stack:
            metadata_context['stack'] = stack
            metadata_lines.append(f"stack: {stack}")
        
        # Add metadata from page metadata
        if metadata.get('language'):
            metadata_context['language'] = metadata['language']
            metadata_lines.append(f"language: {metadata['language']}")
        
        if metadata.get('framework'):
            metadata_context['framework'] = metadata['framework']
            metadata_lines.append(f"framework: {metadata['framework']}")
        
        # Detect patterns
        patterns = self._detect_patterns(content)
        if patterns:
            metadata_context['patterns'] = patterns
            metadata_lines.append(f"patterns: {', '.join(patterns)}")
        
        if not metadata_lines:
            return None
        
        return DockerChunk(
            chunk_id=f"{page_id}-metadata",
            content='\n'.join(metadata_lines),
            chunk_type="metadata",
            context=metadata_context,
            start_line=0,
            end_line=min(20, len(lines) - 1),
            importance_score=1.5  # High importance for initial matching
        )
    
    def _extract_stage_chunks(
        self, 
        content: str, 
        lines: List[str], 
        page_id: str, 
        metadata: Dict[str, Any]
    ) -> List[DockerChunk]:
        """Extract individual stage chunks for multi-stage builds."""
        chunks = []
        
        # Find all FROM statements
        from_pattern = r'^FROM\s+([^\s]+)(?:\s+AS\s+([^\s]+))?'
        from_matches = list(re.finditer(from_pattern, content, re.MULTILINE | re.IGNORECASE))
        
        if len(from_matches) <= 1:
            # Single-stage build - chunk by instruction groups instead
            return self._extract_instruction_group_chunks(content, lines, page_id, metadata)
        
        # Multi-stage build
        for idx, from_match in enumerate(from_matches):
            base_image = from_match.group(1)
            stage_name = from_match.group(2) or f"stage-{idx}"
            
            # Find stage content (from this FROM to next FROM or end)
            start_pos = from_match.start()
            if idx < len(from_matches) - 1:
                end_pos = from_matches[idx + 1].start()
            else:
                end_pos = len(content)
            
            stage_content = content[start_pos:end_pos].strip()
            
            # Analyze stage
            stage_context = {
                'stage_name': stage_name,
                'base_image': base_image,
                'stage_index': idx,
                **self._analyze_stage_content(stage_content)
            }
            
            # Calculate line numbers
            start_line = content[:start_pos].count('\n')
            end_line = content[:end_pos].count('\n')
            
            # Create stage chunk
            chunk_content = f"stage: {stage_name}\nbase: {base_image}\n{stage_content}"
            
            chunks.append(DockerChunk(
                chunk_id=f"{page_id}-stage-{idx}",
                content=chunk_content if len(chunk_content) <= self.max_chunk_size else chunk_content[:self.max_chunk_size],
                chunk_type="stage",
                context=stage_context,
                start_line=start_line,
                end_line=end_line,
                importance_score=1.2  # Stages are important semantic units
            ))
        
        return chunks
    
    def _extract_instruction_group_chunks(
        self,
        content: str,
        lines: List[str],
        page_id: str,
        metadata: Dict[str, Any]
    ) -> List[DockerChunk]:
        """Extract chunks grouped by related instructions."""
        chunks = []
        
        # Group instructions by type
        groups = {
            'setup': [],  # RUN commands that install/setup
            'copy': [],   # COPY/ADD commands
            'config': [], # ENV, WORKDIR, EXPOSE, etc.
            'runtime': [] # CMD, ENTRYPOINT
        }
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith('#'):
                continue
            
            if line_stripped.startswith('RUN'):
                groups['setup'].append(line_stripped)
            elif line_stripped.startswith(('COPY', 'ADD')):
                groups['copy'].append(line_stripped)
            elif line_stripped.startswith(('ENV', 'WORKDIR', 'EXPOSE', 'USER', 'VOLUME')):
                groups['config'].append(line_stripped)
            elif line_stripped.startswith(('CMD', 'ENTRYPOINT')):
                groups['runtime'].append(line_stripped)
        
        # Create chunks for non-empty groups
        idx = 0
        for group_type, instructions in groups.items():
            if instructions:
                chunk_content = '\n'.join(instructions)
                context = {
                    'group_type': group_type,
                    'instruction_count': len(instructions)
                }
                
                chunks.append(DockerChunk(
                    chunk_id=f"{page_id}-group-{idx}",
                    content=chunk_content,
                    chunk_type="instruction_group",
                    context=context,
                    start_line=0,  # Approximate
                    end_line=len(lines),
                    importance_score=1.0
                ))
                idx += 1
        
        return chunks
    
    def _analyze_stage_content(self, stage_content: str) -> Dict[str, Any]:
        """Analyze stage content to extract semantic information."""
        analysis = {
            'has_run': 'RUN' in stage_content.upper(),
            'has_copy': 'COPY' in stage_content.upper() or 'ADD' in stage_content.upper(),
            'has_env': 'ENV' in stage_content.upper(),
            'has_expose': 'EXPOSE' in stage_content.upper(),
            'commands': [],
        }
        
        # Extract RUN commands
        run_pattern = r'RUN\s+(.+?)(?=\n[A-Z]|\Z)'
        runs = re.findall(run_pattern, stage_content, re.IGNORECASE | re.DOTALL)
        analysis['commands'] = [cmd.strip()[:100] for cmd in runs]  # Truncate long commands
        
        return analysis
    
    def _detect_stack(self, content: str) -> Optional[str]:
        """Detect stack/language from Dockerfile content."""
        content_lower = content.lower()
        
        # Check for language-specific patterns
        if 'python' in content_lower or 'pip' in content_lower:
            return 'python'
        if 'node' in content_lower or 'npm' in content_lower or 'yarn' in content_lower:
            return 'node'
        if 'java' in content_lower or 'maven' in content_lower or 'gradle' in content_lower:
            return 'java'
        if 'golang' in content_lower or 'go build' in content_lower:
            return 'go'
        if 'cargo' in content_lower or 'rust' in content_lower:
            return 'rust'
        if 'dotnet' in content_lower or 'nuget' in content_lower:
            return 'dotnet'
        if 'php' in content_lower or 'composer' in content_lower:
            return 'php'
        if 'ruby' in content_lower or 'gem' in content_lower or 'bundle' in content_lower:
            return 'ruby'
        
        return None
    
    def _detect_patterns(self, content: str) -> List[str]:
        """Detect Docker patterns in content."""
        patterns = []
        content_lower = content.lower()
        
        if 'as builder' in content_lower or 'as build' in content_lower:
            patterns.append('multi-stage')
        if 'healthcheck' in content_lower:
            patterns.append('healthcheck')
        if 'user' in content_lower and 'root' not in content_lower:
            patterns.append('non-root')
        if 'apk add' in content_lower or 'apt-get' in content_lower:
            patterns.append('system-packages')
        if 'alpine' in content_lower:
            patterns.append('alpine')
        if 'distroless' in content_lower:
            patterns.append('distroless')
        if 'nginx' in content_lower:
            patterns.append('nginx')
        
        return patterns


class EnhancedDockerRetriever:
    """Enhanced retrieval using semantic Docker chunks."""
    
    def __init__(self):
        self.chunker = DockerfileChunker()
    
    def query_with_chunks(
        self, 
        query_text: str, 
        pages: List[Dict[str, Any]], 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query using enhanced Docker chunking strategy.
        
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
            chunks = self.chunker.chunk_dockerfile(
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
        
        for score, chunk, page in scored_chunks[:top_k * 5]:  # Get more candidates for deduped pages
            page_id = page.get('page_id')

            # Include only best chunk per page to avoid duplicate page IDs.
            if page_id not in seen_pages:
                results.append({
                    'score': score,
                    'page_id': page_id,
                    'title': page.get('title'),
                    'source': page.get('source'),
                    'tags': page.get('tags', []),
                    'content': chunk.content,
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
        chunk: DockerChunk, 
        query_tokens: set, 
        query_context: Dict[str, Any]
    ) -> float:
        """Score chunk relevance with context awareness."""
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
        
        # Stack match
        if query_context.get('stack') and chunk.context.get('stack'):
            if query_context['stack'].lower() == chunk.context['stack'].lower():
                context_bonus += 2.5
        
        # Base image match
        if query_context.get('base_images'):
            chunk_images = chunk.context.get('base_images', [])
            for query_img in query_context['base_images']:
                if any(query_img in img for img in chunk_images):
                    context_bonus += 2.0
        
        # Pattern match
        query_patterns = set(query_context.get('patterns', []))
        chunk_patterns = set(chunk.context.get('patterns', []))
        pattern_overlap = len(query_patterns.intersection(chunk_patterns))
        context_bonus += pattern_overlap * 1.5
        
        # Multi-stage match
        if query_context.get('multi_stage') and chunk.context.get('is_multi_stage'):
            context_bonus += 1.5
        
        return base_score + context_bonus
    
    def _extract_query_context(self, query_text: str) -> Dict[str, Any]:
        """Extract semantic context from query."""
        query_lower = query_text.lower()
        context = {
            'patterns': [],
            'base_images': [],
            'multi_stage': False
        }
        
        # Detect stack
        stacks = {
            'python': ['python', 'pip', 'django', 'flask', 'fastapi'],
            'node': ['node', 'npm', 'yarn', 'javascript', 'typescript'],
            'java': ['java', 'maven', 'gradle', 'spring'],
            'go': ['golang', 'go'],
            'rust': ['rust', 'cargo'],
            'dotnet': ['dotnet', 'c#', 'csharp', 'nuget'],
            'php': ['php', 'composer'],
            'ruby': ['ruby', 'gem', 'bundle']
        }
        
        for stack, keywords in stacks.items():
            if any(keyword in query_lower for keyword in keywords):
                context['stack'] = stack
                break
        
        # Detect patterns
        if 'multi-stage' in query_lower or 'multi stage' in query_lower:
            context['patterns'].append('multi-stage')
            context['multi_stage'] = True
        if 'alpine' in query_lower:
            context['patterns'].append('alpine')
            context['base_images'].append('alpine')
        if 'distroless' in query_lower:
            context['patterns'].append('distroless')
            context['base_images'].append('distroless')
        if 'nginx' in query_lower:
            context['patterns'].append('nginx')
        if 'healthcheck' in query_lower:
            context['patterns'].append('healthcheck')
        if 'non-root' in query_lower or 'security' in query_lower:
            context['patterns'].append('non-root')
        
        return context
    
    def _tokenize(self, text: str) -> set:
        """Tokenize text for matching."""
        return set(re.findall(r'[a-zA-Z0-9_\-.]+', text.lower()))

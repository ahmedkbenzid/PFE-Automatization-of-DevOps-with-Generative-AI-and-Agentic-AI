"""
Demo script to compare basic vs enhanced chunking retrieval.

Run this to see the improvement in action!
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.datasets.dataset_manager import DatasetManager


def print_separator(char="=", length=80):
    """Print a visual separator."""
    print(char * length)


def print_results(results, title="Results"):
    """Pretty print search results."""
    print(f"\n{title}")
    print_separator("-")
    
    if not results:
        print("  No results found")
        return
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   Score: {result['score']}")
        
        if 'chunk_type' in result:
            print(f"   Chunk Type: {result['chunk_type']}")
        
        if 'chunk_context' in result and result['chunk_context']:
            context = result['chunk_context']
            context_items = []
            if context.get('language'):
                context_items.append(f"Language: {context['language']}")
            if context.get('patterns'):
                context_items.append(f"Patterns: {', '.join(context['patterns'])}")
            if context.get('job_name'):
                context_items.append(f"Job: {context['job_name']}")
            if context_items:
                print(f"   Context: {' | '.join(context_items)}")
        
        print(f"   Source: {result.get('source', 'N/A')}")
        
        # Show snippet of content
        content = result.get('content', '')
        snippet = content[:200].replace('\n', ' ')
        if len(content) > 200:
            snippet += "..."
        print(f"   Content: {snippet}")


def compare_retrieval_methods():
    """Compare basic vs enhanced chunking."""
    print_separator("=")
    print("ENHANCED CHUNKING COMPARISON DEMO")
    print_separator("=")
    
    manager = DatasetManager()
    
    # Test queries that benefit from enhanced chunking
    test_queries = [
        "Python test workflow with pytest",
        "Java Spring Boot with SonarQube",
        "Docker build and push to registry",
        "Node.js testing with npm",
        "Deployment to Kubernetes",
    ]
    
    for query in test_queries:
        print(f"\n\n{'='*80}")
        print(f"Query: '{query}'")
        print(f"{'='*80}")
        
        # Test with basic retrieval (if available)
        print("\n[1] BASIC TOKEN OVERLAP (Original Method)")
        print_separator("-")
        try:
            # Access knowledge base with basic mode
            kb = manager.knowledge_base
            basic_results = kb.query(query, top_k=3, use_enhanced=False)
            print_results(basic_results, "Basic Retrieval Results")
        except Exception as e:
            print(f"Basic retrieval error: {e}")
        
        # Test with enhanced chunking
        print("\n\n[2] ENHANCED SEMANTIC CHUNKING (New Method)")
        print_separator("-")
        try:
            enhanced_results = manager.retrieve_knowledge(query, top_k=3)
            print_results(enhanced_results, "Enhanced Retrieval Results")
        except Exception as e:
            print(f"Enhanced retrieval error: {e}")
        
        print("\n" + "="*80)
        print("COMPARISON SUMMARY")
        print("="*80)
        print("✅ Enhanced chunking provides:")
        print("   - Chunk-level granularity (metadata, job, step)")
        print("   - Context-aware scoring (language, patterns, triggers)")
        print("   - Better relevance ranking with importance weighting")
        print("   - Preserved semantic context in results")


def demo_chunk_types():
    """Demonstrate different chunk types."""
    print("\n\n" + "="*80)
    print("CHUNK TYPE DEMONSTRATION")
    print("="*80)
    
    manager = DatasetManager()
    
    # Queries that should match different chunk types
    queries = {
        "workflow metadata": "What workflows trigger on push?",
        "job-level": "Show me a build job",
        "step-level": "How to cache dependencies?",
    }
    
    for expected_type, query in queries.items():
        print(f"\n\nQuery: '{query}'")
        print(f"Expected chunk type: {expected_type}")
        print_separator("-")
        
        results = manager.retrieve_knowledge(query, top_k=2)
        
        if results:
            for i, result in enumerate(results, 1):
                chunk_type = result.get('chunk_type', 'unknown')
                print(f"\n{i}. {result['title']}")
                print(f"   Chunk Type: {chunk_type} {'✅' if expected_type in chunk_type else ''}")
                print(f"   Score: {result['score']}")


def demo_context_extraction():
    """Demonstrate query context extraction."""
    print("\n\n" + "="*80)
    print("QUERY CONTEXT EXTRACTION DEMO")
    print("="*80)
    
    from src.datasets.enhanced_chunker import EnhancedChunkRetriever
    
    retriever = EnhancedChunkRetriever()
    
    test_queries = [
        "Python pytest workflow",
        "Java Maven build with Docker",
        "Deploy to Kubernetes with Helm",
        "Node.js tests on pull request",
        "SonarQube code quality check",
    ]
    
    for query in test_queries:
        context = retriever._extract_query_context(query)
        
        print(f"\n\nQuery: '{query}'")
        print_separator("-")
        print(f"  Language: {context.get('language', 'Not detected')}")
        print(f"  Patterns: {', '.join(context.get('patterns', [])) or 'None'}")
        print(f"  Triggers: {', '.join(context.get('triggers', [])) or 'None'}")
        print(f"  Job Terms: {', '.join(context.get('job_terms', [])) or 'None'}")
        print(f"  Actions: {', '.join(context.get('actions', [])) or 'None'}")


def main():
    """Run all demos."""
    try:
        # Demo 1: Compare basic vs enhanced
        compare_retrieval_methods()
        
        # Demo 2: Show chunk types
        demo_chunk_types()
        
        # Demo 3: Show context extraction
        demo_context_extraction()
        
        print("\n\n" + "="*80)
        print("DEMO COMPLETE! ✅")
        print("="*80)
        print("\nKey Takeaways:")
        print("  1. Enhanced chunking breaks workflows into semantic pieces")
        print("  2. Context-aware scoring improves relevance")
        print("  3. Different chunk types for different query needs")
        print("  4. Automatic query understanding (language, patterns, etc.)")
        print("\nTo use in your code:")
        print("  from src.datasets.dataset_manager import DatasetManager")
        print("  manager = DatasetManager()")
        print("  results = manager.retrieve_knowledge('your query', top_k=5)")
        
    except Exception as e:
        print(f"\n❌ Error running demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

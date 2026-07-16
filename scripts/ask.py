import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.query_classifier import classify
from src.pipeline.guardrails import apply_input_guardrails
from src.pipeline.retriever import retrieve
from src.pipeline.generator import generate_response, generate_refusal, generate_pii_block

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/ask.py <query>")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    print(f"Query: {query}")
    print("-" * 50)
    
    # 1. Classification
    query_type = classify(query)
    print(f"Classification: {query_type}")
    
    # 2. Input Guardrails
    sanitized_query, error = apply_input_guardrails(query)
    if error:
        print(f"\n[BLOCKED BY INPUT GUARDRAILS]")
        print(error)
        return
        
    # 3. Routing
    if query_type == "advisory":
        response = generate_refusal(sanitized_query)
    elif query_type == "pii_detected":
        response = generate_pii_block(sanitized_query)
    else:
        # Factual query - full pipeline
        print("Retrieving context from vector store...")
        try:
            chunks = retrieve(sanitized_query, top_k=3)
            print(f"Found {len(chunks)} chunks.")
            
            print("Generating response via Groq API...")
            response = generate_response(sanitized_query, chunks)
        except Exception as e:
            print(f"Error during retrieval/generation: {e}")
            return
            
    # 4. Output
    print("\n" + "=" * 50)
    print("FINAL RESPONSE")
    print("=" * 50)
    print(response.get("answer", ""))
    
    if response.get("source"):
        print("\nCitation:", response.get("source"))
    if response.get("last_updated"):
        print("Last Updated:", response.get("last_updated"))

if __name__ == "__main__":
    main()

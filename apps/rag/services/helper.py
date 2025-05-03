import numpy as np
from typing import Dict, Any, Optional, List, Tuple, Set
import re
import google.generativeai as genai
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def compress_and_filter_documents(
    document_results: List[Any],
    query_text: str,
    similarity_threshold: float = 0.7,
    gemini_api_key: Optional[str] = None,
    high_confidence_threshold: float = 0.85  # Added parameter
) -> List[Dict[str, Any]]:
    """
    Post-retrieval filtering to remove irrelevant content from retrieved documents.
    
    Args:
        document_results: List of retrieved document results
        query_text: User question
        similarity_threshold: Minimum similarity score to keep a document
        gemini_api_key: API key for Gemini
        high_confidence_threshold: Threshold for high-confidence matches
        
    Returns:
        List of filtered and compressed documents
    """
    # First filter by similarity score
    filtered_docs = [r for r in document_results if hasattr(r, 'score') and r.score >= similarity_threshold]
    
    if not filtered_docs:
        logger.info(f"No documents passed the similarity threshold of {similarity_threshold}")
        return []
    
    # Process documents into standard format
    processed_docs = []
    for i, result in enumerate(filtered_docs):
        try:
            doc_text = result.payload.get('text', '')
            if not doc_text:
                logger.warning(f"Document {result.id} has empty text, skipping")
                continue
                
            processed_docs.append({
                "id": result.id,
                "text": doc_text,
                "score": result.score,
                "metadata": {k: v for k, v in result.payload.items() if k != 'text'},
                "compressed": False  # Track if we've compressed this doc
            })
        except AttributeError as e:
            logger.error(f"Error processing document: {e}")
            continue
    
    # For top documents above a high threshold, we can skip compression (optimization)
    top_docs = [doc for doc in processed_docs if doc["score"] >= high_confidence_threshold]
    
    # If we have sufficient high-confidence docs, we might not need compression
    if len(top_docs) >= 2:
        logger.info(f"Found {len(top_docs)} high-confidence documents. Skipping compression.")
        return processed_docs  # Return all docs without compression
    
    # Otherwise, perform LLM-based document compression/filtering
    try:
        # Configure Gemini
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        
        # Use a more specific model string
        try:
            model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini 2.5 Pro: {e}. Falling back to Gemini Pro.")
            model = genai.GenerativeModel('gemini-pro')
        
        # Create copies rather than modifying in place
        compressed_docs = []
        
        # Process each document - keep only relevant segments
        for i, doc in enumerate(processed_docs):
            # Skip very high confidence docs
            if doc["score"] >= high_confidence_threshold:
                compressed_docs.append(doc)
                continue
                
            # Compress document content
            prompt = f"""
            You are a document compressor that helps extract only the parts of a document 
            that are relevant to a specific query.
            
            QUERY: "{query_text}"
            
            DOCUMENT CONTENT:
            {doc['text']}
            
            Extract ONLY the specific sentences or paragraphs that directly relate to answering 
            the query. Maintain the exact wording from the original document. 
            Do not add any commentary, just extract the relevant parts.
            If nothing in the document is relevant to the query, respond with "NO_RELEVANT_CONTENT".
            """
            
            try:
                response = model.generate_content(prompt)
                compressed_text = response.text.strip()
                
                if compressed_text == "NO_RELEVANT_CONTENT":
                    logger.info(f"Document {doc['id']} marked as not relevant by LLM")
                    continue  # Skip adding this document
                else:
                    # Create a new document with compressed content
                    compressed_doc = doc.copy()
                    compressed_doc["compressed"] = True
                    compressed_doc["text"] = compressed_text
                    compressed_doc["original_length"] = len(doc["text"])
                    compressed_doc["compressed_length"] = len(compressed_text)
                    compressed_docs.append(compressed_doc)
            except Exception as e:
                logger.warning(f"Error compressing document {doc['id']}: {e}")
                compressed_docs.append(doc)  # Keep original on error
        
        # Return the new list of documents
        return [doc for doc in compressed_docs if doc["text"].strip()]
        
    except Exception as e:
        logger.error(f"Error in document compression pipeline: {e}")
        # On error, return the original filtered docs
        return processed_docs

def extract_keywords_from_query(query_text: str) -> Set[str]:
    """
    Extract meaningful keywords from a query to assess document relevance.
    
    Args:
        query_text: User question
        
    Returns:
        Set of important keywords
    """
    # Convert to lowercase
    text = query_text.lower()
    
    # Remove common stop words
    stop_words = {
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'by', 'for',
        'with', 'about', 'against', 'between', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'is',
        'am', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'having', 'do', 'does', 'did', 'doing', 'i', 'me', 'my', 'myself', 'we',
        'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself',
        'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
        'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs',
        'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these',
        'those', 'would', 'should', 'could', 'ought', 'of', 'if', 'then', 'else',
        'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
        'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
        'so', 'than', 'too', 'very', 'can', 'will', 'just', 'don', 'should', 'now'
    }
    
    # Split into words and remove stopwords
    words = re.findall(r'\b\w+\b', text)
    keywords = {word for word in words if word not in stop_words and len(word) > 1}
    
    return keywords

def assess_document_relevance(
    query_text: str,
    document_text: str,
    gemini_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Use Gemini to assess if a document is relevant to the query.
    
    Args:
        query_text: User question
        document_text: Document content
        gemini_api_key: API key for Gemini
        
    Returns:
        Dictionary with relevance assessment and confidence
    """
    # First perform a simple keyword-based check
    query_keywords = extract_keywords_from_query(query_text)
    
    if not query_keywords:
        logger.warning("No meaningful keywords extracted from query")
        return {
            "is_relevant": True,  # Default to keeping document if we can't extract keywords
            "confidence": "low",
            "method": "keyword_analysis_failed",
            "explanation": "Could not extract meaningful keywords from query"
        }
    
    doc_text_lower = document_text.lower()
    
    # Count keyword matches
    keyword_matches = sum(1 for keyword in query_keywords if keyword in doc_text_lower)
    keyword_coverage = keyword_matches / len(query_keywords) if query_keywords else 0
    
    logger.info(f"Keyword analysis: {keyword_matches}/{len(query_keywords)} keywords matched")
    
    # If almost no keywords match, quick reject
    if keyword_coverage < 0.2 and len(query_keywords) >= 3:
        return {
            "is_relevant": False,
            "confidence": "high",
            "method": "keyword_analysis",
            "explanation": f"Document contains few query keywords ({keyword_matches}/{len(query_keywords)})"
        }
    
    # If document is very long, truncate for LLM processing
    max_doc_length = 4000
    original_length = len(document_text)
    truncated = False
    
    if len(document_text) > max_doc_length:
        # Keep beginning, middle and end for better context
        third_length = max_doc_length // 3
        document_text = (
            document_text[:third_length] + 
            "... [middle content omitted] ..." + 
            document_text[len(document_text)//2 - third_length//2:len(document_text)//2 + third_length//2] +
            "... [middle content omitted] ..." +
            document_text[-third_length:]
        )
        truncated = True
    
    # For borderline cases, use LLM judgment
    try:
        # Configure Gemini if API key provided
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        
        try:
            model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini 2.5 Pro: {e}. Falling back to Gemini Pro.")
            model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        Assess if the following document is relevant to this specific query:
        
        QUERY: "{query_text}"
        
        DOCUMENT{' (truncated)' if truncated else ''}:
        {document_text}
        
        Answer with either "RELEVANT" or "NOT_RELEVANT" followed by a brief explanation.
        Focus specifically on whether the document contains information that helps answer the query.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip().lower()
        
        is_relevant = "relevant" in response_text[:20] and "not relevant" not in response_text[:20]
        
        # Extract explanation if available
        explanation = response_text.split("\n")[1] if "\n" in response_text else response_text
        
        return {
            "is_relevant": is_relevant,
            "confidence": "high",
            "method": "llm_analysis",
            "explanation": explanation,
            "truncated": truncated,
            "original_length": original_length
        }
        
    except Exception as e:
        logger.error(f"Error in LLM relevance assessment: {e}")
        # Fallback to keyword-based assessment on error
        is_relevant = keyword_coverage >= 0.5 or keyword_matches >= 3
        
        return {
            "is_relevant": is_relevant,
            "confidence": "medium",
            "method": "keyword_fallback",
            "explanation": f"Document contains {keyword_matches}/{len(query_keywords)} query keywords"
        }

def create_compact_context(
    filtered_documents: List[Dict[str, Any]],
    query_text: str,
    max_tokens: int = 8000,
    gemini_api_key: Optional[str] = None,
    include_metadata_fields: List[str] = ["title", "source", "date", "author"]
) -> str:
    """
    Create a compact context from filtered documents, prioritizing most relevant content.
    
    Args:
        filtered_documents: List of filtered documents
        query_text: User question
        max_tokens: Maximum approximate token limit for context
        gemini_api_key: API key for Gemini
        include_metadata_fields: Metadata fields to include in context
        
    Returns:
        Formatted context string with document segments
    """
    # Sort documents by score (highest first)
    sorted_docs = sorted(filtered_documents, key=lambda x: x["score"], reverse=True)
    
    # Calculate approximate tokens (rough estimate: 4 chars ~ 1 token)
    total_chars = 0
    approx_max_chars = max_tokens * 4
    
    context_parts = []
    
    for i, doc in enumerate(sorted_docs):
        # Format document with metadata if available
        doc_header = f"Document {i+1} (Score: {doc['score']:.2f})"
        
        # Add metadata if available and not too long
        if doc.get("metadata"):
            metadata_str = ", ".join(
                f"{k}: {v}" for k, v in doc["metadata"].items() 
                if k in include_metadata_fields and v and isinstance(v, (str, int, float))
            )
            if metadata_str:
                doc_header += f" | {metadata_str}"
        
        # Check if this is a compressed document
        compression_info = ""
        if doc.get("compressed"):
            original = doc.get("original_length", len(doc.get("text", "")))
            compressed = doc.get("compressed_length", len(doc.get("text", "")))
            if original > compressed:
                percent_reduced = (original - compressed) / original * 100
                compression_info = f" [Compressed: {percent_reduced:.1f}% reduction]"
        
        doc_content = f"{doc_header}{compression_info}:\n{doc.get('text', '')}\n\n"
        doc_chars = len(doc_content)
        
        # Check if adding this document would exceed token limit
        if total_chars + doc_chars <= approx_max_chars:
            context_parts.append(doc_content)
            total_chars += doc_chars
        else:
            # Try to include partial content for first document if we have nothing yet
            if not context_parts:
                # Truncate text to fit
                avail_chars = approx_max_chars - len(doc_header) - 15
                truncated_text = doc.get('text', '')[:avail_chars] + "... [truncated]"
                context_parts.append(f"{doc_header}:\n{truncated_text}\n\n")
            else:
                context_parts.append(f"[Additional documents omitted due to context length limits]\n")
            break
    
    # If we have very little content but should have some documents, something may be wrong
    if total_chars < 100 and filtered_documents:
        logger.warning("Warning: Created context is suspiciously small despite having documents")
    
    return "".join(context_parts)

def get_document_topics(
    document_text: str,
    gemini_api_key: Optional[str] = None,
    max_topics: int = 5
) -> List[str]:
    """
    Extract main topics from a document using Gemini.
    
    Args:
        document_text: Document content
        gemini_api_key: API key for Gemini
        max_topics: Maximum number of topics to extract
        
    Returns:
        List of main topics as strings
    """
    # Truncate document if very long
    original_length = len(document_text)
    if len(document_text) > 10000:
        document_text = document_text[:10000] + "... [truncated]"
    
    try:
        # Configure Gemini
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        
        try:
            model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini 2.5 Pro: {e}. Falling back to Gemini Pro.")
            model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        Extract the {max_topics} main topics or key concepts from this document.
        Return them as a comma-separated list with no additional text.
        
        Document:
        {document_text}
        
        Main topics (comma-separated):
        """
        
        response = model.generate_content(prompt)
        topics_text = response.text.strip()
        
        # Clean up response and split into list
        topics = [t.strip() for t in topics_text.split(',')]
        topics = [t for t in topics if t and len(t) > 1]  # Filter out empty or single-char topics
        
        return topics[:max_topics]
        
    except Exception as e:
        logger.error(f"Error extracting document topics: {e}")
        
        # Fallback to simple keyword extraction
        words = re.findall(r'\b\w+\b', document_text.lower())
        word_freq = {}
        
        # Count word frequency (excluding stop words)
        stop_words = {'the', 'and', 'is', 'in', 'to', 'of', 'a', 'for', 'with', 'on', 'at'}
        for word in words:
            if word not in stop_words and len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Get most frequent words as topics
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        topics = [word for word, _ in top_words[:max_topics]]
        return topics

        
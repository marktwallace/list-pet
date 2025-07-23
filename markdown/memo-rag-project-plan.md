# Memo RAG Implementation Project Plan

## Overview

This project implements a RAG-like recall mechanism where users can uprate messages to create retrievable memos, and the LLM can emit `<recall>` tags to retrieve relevant contextual examples via embedding similarity search.

**Key Features:**
- User uprates (👍) create persistent memos with embeddings
- LLM emits `<recall>query</recall>` to retrieve relevant examples
- Retrieved memos are injected as `<memo>` content into LLM context
- Team-shared memory across conversations

---

## Architecture Changes

### Database Schema Extensions
```sql
-- New memo storage table in pet_meta schema
CREATE TABLE pet_meta.memo_store (
    id INTEGER PRIMARY KEY,
    content TEXT,                  -- Full <memo> XML block
    embedding DOUBLE[],            -- 1536-dim vector from text-embedding-3-small
    created_at TIMESTAMP,
    source TEXT,                   -- 'uprated_by_user'
    user_message TEXT,             -- Original user prompt
    message_ids TEXT[]             -- Traceability to source messages
);

-- Add memo tracking to existing message_log table
ALTER TABLE pet_meta.message_log ADD COLUMN IF NOT EXISTS memo_id INTEGER;
ALTER TABLE pet_meta.message_log ADD COLUMN IF NOT EXISTS memo_queue_status TEXT; -- 'pending', 'processed', 'failed'

-- Create memo processing queue table
CREATE TABLE pet_meta.memo_queue (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed', 'cancelled'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    error_message TEXT,
    FOREIGN KEY (message_id) REFERENCES pet_meta.message_log(id)
);
```

### New Components
- **MemoManager** (`src/memo_manager.py`): Handles embedding generation, storage, and retrieval
- **EmbeddingService** (`src/embedding_service.py`): OpenAI API wrapper for text-embedding-3-small
- **MemoQueue** (`src/memo_queue.py`): Asynchronous memo creation and deletion queue
- Extended **MetadataDatabase** (`src/metadata_database.py`): Memo CRUD operations
- Extended **parsing** (`src/parsing.py`): Already supports `<recall>` and `<memo>` tags via existing get_elements()

### Integration Points
- **Feedback System**: Hook thumbs-up (score=1) → create memo
- **Message Processing**: Detect `<recall>` → inject `<memo>` before LLM
- **UI Display**: Render `<memo>` tags like other XML elements

---

## Implementation Phases

### Phase 1: Core Infrastructure ✅
- [ ] **Database Schema** - Create memo_store table
- [ ] **Embedding Service** - OpenAI API integration
- [ ] **Memo CRUD** - Basic storage and retrieval operations
- [ ] **Unit Tests** - Test core memo operations

### Phase 2: Feedback Integration ✅
- [ ] **Memo Queue System** - Implement asynchronous memo creation queue for LLM API calls
- [ ] **Uprate Hook** - Connect thumbs-up button to `memo_queue.enqueue_memo_creation(message_id)`
- [ ] **Memo ID Tracking** - Add memo_id and memo_queue_status columns to message_log table
- [ ] **Memo Content Extraction** - Format reasoning/sql/chart content excluding dataframes
- [ ] **Downvote Cleanup** - Connect thumbs-down to `memo_queue.cancel_or_delete_memo(message_id)`
- [ ] **Queue Processing** - Background worker to process memo creation tasks
- [ ] **Integration Tests** - Test feedback-to-memo workflow with queue handling

### Phase 3: Recall Processing ✅
- [ ] **Recall Tag Detection** - Add to `generate_llm_response()` and pending processing loop
- [ ] **Pending Recall Processing** - Add `sess.pending_recall` and `process_recall_query()` following SQL pattern
- [ ] **Similarity Search** - Cosine similarity memo retrieval via `memo_manager.recall_memos()`
- [ ] **Memo Injection** - Insert `<memo>` content as USER_ROLE message before LLM continues
- [ ] **UI Display** - Render memo tags in `display_message()` similar to other XML elements

### Phase 4: Polish & Performance ✅
- [ ] **Error Handling** - Robust failure recovery
- [ ] **Performance Testing** - Test with 100+ memos
- [ ] **Logging** - Comprehensive operation tracking
- [ ] **Documentation** - User guides and system docs

---

## Code Integration Points

### streamlit_ui.py Modifications

#### 1. Add Recall Processing to Pending Loop (Lines 1013-1026)
```python
# Current pattern for SQL/Python/Chart processing:
if sess.pending_python and sess.pending_python[0]:
    python_tuple = sess.pending_python.pop(0)
    if process_python_code(python_tuple):
        st.rerun()

# ADD: Recall processing following same pattern
if sess.pending_recall and sess.pending_recall[0]:
    recall_tuple = sess.pending_recall.pop(0)
    if process_recall_query(recall_tuple):
        st.rerun()
```

#### 2. Modify generate_llm_response() to Detect Recall Tags (Lines 801-814)
```python
def generate_llm_response():
    sess = st.session_state
    sess.pending_response = False
    response = sess.llm_handler.generate_response()
    if response is None:
        return False
    conv_manager.add_message(role=ASSISTANT_ROLE, content=response)
    msg = get_elements(response)
    sess.pending_sql = list(enumerate(msg.get("sql", [])))
    sess.pending_chart = list(enumerate(msg.get("chart", [])))
    sess.pending_python = list(enumerate(msg.get("python", [])))
    # ADD: Process recall tags
    sess.pending_recall = list(enumerate(msg.get("recall", [])))
    return True
```

#### 3. Modify Thumbs-Up Handler to Use Queue (Lines 507-513)
```python
# Current synchronous feedback handling:
if st.button("👍", key=f"thumbs_up_{idx}", help="Thumbs up", type=up_type):
    new_score = 0 if message.get('feedback_score', 0) == 1 else 1
    metadata_db.update_feedback_score(message['id'], new_score)
    # ADD: Queue-based memo handling
    if new_score == 1:
        memo_queue.enqueue_memo_creation(message['id'])
    elif new_score == 0 and message.get('memo_id'):
        memo_queue.cancel_or_delete_memo(message['id'])
    _reload_and_rerun(sess, metadata_db)
```

#### 4. Add Memo Display to XML Element Rendering (Lines 470-500)
```python
# Current pattern for SQL, Python, etc:
if "sql" in msg:
    for item in msg["sql"]:
        with st.expander(title_text(item["content"]), expanded=False):
            st.code(item["content"])

# ADD: Memo display
if "memo" in msg:
    for item in msg["memo"]:
        with st.expander("📝 Retrieved Memo", expanded=True):
            # Parse and display memo content with proper formatting
            memo_elements = get_elements(item["content"])
            if "reasoning" in memo_elements:
                st.markdown("**Reasoning:**")
                st.markdown(memo_elements["reasoning"][0]["content"])
            if "sql" in memo_elements:
                st.markdown("**SQL:**")
                st.code(memo_elements["sql"][0]["content"])
```

#### 5. Session State Initialization (Lines 406-422)
```python
# ADD to init_session_state in ConversationManager:
if "pending_recall" not in sess:
    sess.pending_recall = []
if "memo_queue" not in sess:
    sess.memo_queue = MemoQueue()
```

## Technical Implementation Details

### Memo Content Extraction
```python
def extract_memo_content(message):
    """Extract memo-worthy content from uprated message"""
    elements = get_elements(message["content"])
    memo_content = "<memo>\n"
    
    # Include reasoning if present
    if "reasoning" in elements:
        memo_content += f"<reasoning>\n{elements['reasoning'][0]['content']}\n</reasoning>\n"
    
    # Include SQL with high weight for embedding
    if "sql" in elements:
        memo_content += f"<sql>\n{elements['sql'][0]['content']}\n</sql>\n"
    
    # Include chart configurations
    if "chart" in elements:
        memo_content += f"<chart>\n{elements['chart'][0]['content']}\n</chart>\n"
    
    # Exclude dataframe content (runtime-generated)
    memo_content += "</memo>"
    return memo_content
```

### Embedding Strategy
- **Text for Embedding**: User prompt + reasoning content + SQL content
- **High Weight Fields**: SQL queries (core business logic)
- **Excluded Fields**: Dataframe content (too volatile)
- **Model**: `text-embedding-3-small` (1536 dimensions)

### Similarity Search
```python
def recall_memos(query_text, top_k=1):
    """Retrieve most similar memos using cosine similarity"""
    query_embedding = embedding_service.get_embedding(query_text)
    
    # Get all memos with embeddings
    memos = metadata_db.get_all_memos()
    
    # Calculate similarities
    similarities = []
    for memo in memos:
        similarity = cosine_similarity(query_embedding, memo['embedding'])
        similarities.append((similarity, memo))
    
    # Return top matches
    similarities.sort(reverse=True)
    return [memo for _, memo in similarities[:top_k]]
```

### Message Processing Pipeline

#### Synchronous Recall Processing (Like SQL Tags)
```python
# In streamlit_ui.py main() function, add to pending processing loop:
if sess.pending_recall and sess.pending_recall[0]:
    recall_tuple = sess.pending_recall.pop(0)
    if process_recall_query(recall_tuple):
        st.rerun()

def process_recall_query(recall_tuple):
    """Process a recall query synchronously and inject memo content"""
    sess = st.session_state
    recall_idx, recall_item = recall_tuple
    query_text = recall_item["content"]
    
    # Retrieve relevant memos via similarity search
    relevant_memos = memo_manager.recall_memos(query_text, top_k=1)
    
    if relevant_memos:
        # Inject memo content as USER_ROLE message
        memo_content = f'<memo>\n{relevant_memos[0]["content"]}\n</memo>\n'
        conv_manager.add_message(role=USER_ROLE, content=memo_content)
    
    return True
```

#### Asynchronous Memo Creation (Queue-Based)
```python
# Thumbs-up processing becomes queue-based
def handle_thumbs_up(message_id, new_score):
    if new_score == 1:
        # Enqueue memo creation work
        memo_queue.enqueue_memo_creation(message_id)
    elif new_score == 0:
        # Dequeue/cancel pending work or delete existing memo
        memo_queue.cancel_or_delete_memo(message_id)

class MemoQueue:
    def enqueue_memo_creation(self, message_id):
        """Queue memo creation work for background processing"""
        # Insert into memo_queue table with status='pending'
        # Update message_log.memo_queue_status = 'pending'
        
    def cancel_or_delete_memo(self, message_id):
        """Cancel pending work or delete existing memo by message_id"""
        # If memo exists: delete from memo_store, update message_log.memo_id = NULL
        # If in queue: update memo_queue.status = 'cancelled'
        
    def process_queue(self):
        """Background worker to process memo creation tasks"""
        # Poll memo_queue for status='pending'
        # For each: extract memo content, generate embedding, store in memo_store
        # Update memo_queue.status and message_log.memo_id on completion
        
    def is_queue_processing_available(self):
        """Check if background processing is available"""
        # Could be Streamlit timer-based or external worker
        # For MVP: process during idle time in main UI loop
```

---

## Testing Strategy

### Unit Tests
- **Embedding Generation**: Test OpenAI API integration and error handling
- **Memo Storage**: Test CRUD operations and data integrity
- **Similarity Search**: Test vector operations and ranking accuracy
- **Content Extraction**: Test memo formatting from various message types

### Integration Tests
- **Feedback Workflow**: Test uprate → memo creation → storage
- **Recall Workflow**: Test `<recall>` → similarity search → `<memo>` injection
- **Multi-Message Memos**: Test memo creation from conversation segments
- **Edge Cases**: Empty results, malformed content, API failures

### Performance Tests
- **Embedding Latency**: Test response times for embedding generation
- **Search Performance**: Test similarity search with 100+ memos
- **Memory Usage**: Test embedding storage and retrieval efficiency
- **Concurrent Access**: Test multiple users accessing memo store

### User Acceptance Tests
- **Workflow Validation**: Test complete user journey from uprate to recall
- **Relevance Quality**: Manually verify memo retrieval accuracy
- **UI Responsiveness**: Test interface performance with memo operations
- **Error Recovery**: Test graceful handling of service failures

---

## Risk Mitigation

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenAI API failures | High | Implement retry logic, fallback to exact text search |
| Embedding storage size | Medium | Monitor database growth, implement memo pruning |
| Search performance | Medium | Add indexing, consider vector databases for scale |
| Memory leaks | Medium | Implement proper cleanup, monitor session state |

### User Experience Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Poor memo relevance | High | Tune embedding strategy, allow user feedback |
| Slow recall responses | Medium | Cache embeddings, optimize similarity search |
| Confusing UI | Low | Clear visual indicators for memo content |
| Data loss | High | Robust backup strategy, transaction handling |

---

## Success Metrics

### Functional Metrics
- [ ] All uprated messages successfully create memos
- [ ] `<recall>` tags consistently retrieve relevant memos
- [ ] Memo content properly excludes volatile dataframe data
- [ ] Search returns results in <2 seconds for 100+ memos

### Quality Metrics
- [ ] >80% user satisfaction with memo relevance
- [ ] <5% false positive/negative rates in similarity search
- [ ] Zero data corruption incidents
- [ ] 99.9% uptime for memo operations

### Performance Metrics
- [ ] Embedding generation: <3 seconds per memo
- [ ] Similarity search: <1 second for 100 memos
- [ ] Memory usage: <10MB per 100 stored memos
- [ ] Database growth: <1MB per day typical usage

---

## Deployment Plan

### Development Environment
1. **Local Testing**: Implement and test on development database
2. **Feature Flags**: Enable memo functionality via environment variable
3. **Debug Logging**: Comprehensive logging for troubleshooting
4. **Mock Services**: Fallback for OpenAI API during development

### Staging Environment
1. **Integration Testing**: Full workflow testing with realistic data
2. **Performance Validation**: Load testing with simulated memo volumes
3. **User Acceptance**: Beta testing with select users
4. **Rollback Planning**: Quick disable mechanism if issues arise

### Production Deployment
1. **Gradual Rollout**: Enable for subset of users initially
2. **Monitoring**: Real-time tracking of memo operations and performance
3. **Support Documentation**: User guides and troubleshooting procedures
4. **Backup Verification**: Ensure memo data included in backup strategy

---

## Future Enhancements

### Short Term (Next Sprint)
- **Multiple Memo Return**: Return top-N memos instead of just top-1
- **Memo Management UI**: Visual interface for viewing/managing stored memos
- **Usage Analytics**: Track memo creation and recall frequency
- **Improved Extraction**: Better handling of multi-message conversations

### Medium Term (Next Quarter)
- **Time Decay**: Weight recent memos higher than older ones
- **User-Specific Memos**: Option for private vs shared memo storage
- **Memo Categories**: Tag memos by domain (SQL, charts, analysis, etc.)
- **Advanced Search**: Hybrid keyword + semantic search

### Long Term (Future Releases)
- **Vector Database**: Migration to specialized vector store for scale
- **Fine-tuned Embeddings**: Custom embedding models for domain-specific content
- **Collaborative Filtering**: Recommend memos based on user behavior
- **Export/Import**: Memo portability between environments

---

## Open Questions & Decisions Needed

### Technical Decisions
- [ ] **LLM Memo Generation**: Should LLM generate memo content or use runtime snapshot?
- [ ] **Multiple Recalls**: Support multiple `<recall>` tags in single message?
- [ ] **Embedding Model**: Stick with text-embedding-3-small or explore alternatives?
- [ ] **Storage Format**: JSON arrays for message_ids or normalized table?

### UX Decisions
- [ ] **Memo Visibility**: Should users see which memos were retrieved?
- [ ] **Relevance Feedback**: Allow users to rate memo relevance?
- [ ] **Memo Editing**: Support manual memo editing/curation?
- [ ] **Sharing Controls**: Team vs personal memo visibility controls?

### Operational Decisions
- [ ] **Retention Policy**: How long to keep memos? Auto-pruning strategy?
- [ ] **Rate Limiting**: Limits on memo creation to prevent abuse?
- [ ] **Cost Management**: OpenAI API usage budgets and monitoring?
- [ ] **Data Privacy**: Memo content handling and user consent?

---

*This document will be updated as implementation progresses and decisions are made.* 
# Conversational Memory Management System

## Overview

This project implements a conversational memory management system where detailed user feedback is curated into high-quality memories through AI-assisted workflows. The system replaces automated memory creation with a high-touch, conversational interface for careful memory construction and management.

**Key Features:**
- **Conversational Interface**: Memory management through specialized chat conversations
- **AI-Assisted Curation**: LLM helps analyze, generalize, and improve memories
- **Human Oversight**: All memory operations require human approval
- **Synthetic Memory Creation**: Transform negative feedback into corrective memories
- **Memory Enhancement**: Iteratively improve existing memories with new insights
- **Recall Integration**: LLM emits `<recall>` tags to retrieve relevant memories
- **Team-Shared Memory**: Curated knowledge base across conversations

---

## Architecture Changes

### Database Schema Extensions
```sql
-- Memory storage table for curated memories
CREATE TABLE pet_meta.memories (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,           -- Memory content with reasoning
    embedding DOUBLE[],              -- 1536-dim vector from text-embedding-3-small
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_feedback_ids TEXT[],      -- Traceability to source feedback
    memory_type TEXT,                -- 'curated', 'synthetic', 'enhanced' 
    usage_count INTEGER DEFAULT 0,   -- Track memory retrieval frequency
    quality_score REAL              -- Human/AI quality assessment
);

-- Enhanced feedback details table (already implemented)
CREATE TABLE pet_meta.feedback_details (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL,
    feedback_type VARCHAR NOT NULL,  -- 'thumbs_up' or 'thumbs_down'
    remember_uprate BOOLEAN,         -- User wants this remembered
    description_text TEXT,           -- Text for memory creation
    what_was_wrong TEXT,             -- Thumbs down: what was wrong
    what_user_wanted TEXT,           -- Thumbs down: desired behavior
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES pet_meta.message_log(id)
);
```

### Conversation Type Architecture
- **Developer Mode Access**: Memory management only available in dev mode
- **Separate Conversation Type**: "Memories:" prefix triggers memory management mode
- **Specialized Prompts**: Memory-specific system prompts and welcome messages
- **Memory Tools**: Custom tool set for metadata queries and memory operations

### New Components
- **Memory Management Prompts**: Specialized prompts for memory curation workflows
- **Memory Tools**: `<metadata_sql>`, `<memory_action>`, `<embedding_analysis>` 
- **EmbeddingService** (`src/embedding_service.py`): OpenAI API wrapper for embeddings
- Extended **MetadataDatabase**: Memory CRUD operations and feedback details
- Extended **parsing** (`src/parsing.py`): Memory management tool support

### Integration Points
- **Feedback Collection**: Enhanced thumbs up/down dialogs capture detailed feedback
- **Memory Conversations**: Separate conversation type with memory-focused tools
- **Recall Processing**: Detect `<recall>` → inject `<memo>` before LLM continues
- **UI Display**: Render `<memo>` tags and memory management interfaces

---

## Implementation Phases

### Phase 1: Enhanced Feedback System ✅
- [x] **Feedback Dialogs** - Thumbs up/down dialogs for detailed feedback collection
- [x] **Database Schema** - feedback_details table with comprehensive feedback fields
- [x] **Database Operations** - CRUD methods for feedback_details management
- [x] **Dialog Integration** - Connect dialogs to thumbs up/down buttons
- [x] **Context-Aware Defaults** - Extract preceding user message for dialog defaults

### Phase 2: Memory Management Infrastructure 
- [ ] **Memory Database Schema** - Create memories table with embeddings and metadata
- [ ] **Embedding Service** - OpenAI text-embedding-3-small integration
- [ ] **Memory CRUD Operations** - Database methods for memory management
- [ ] **Conversation Type Detection** - "Memories:" prefix triggers memory mode
- [ ] **Memory Management Prompts** - Specialized system prompts and instructions

### Phase 3: Memory Management Tools
- [ ] **Metadata SQL Tool** - `<metadata_sql>` for querying feedback and memories
- [ ] **Memory Action Tool** - `<memory_action>` for create/update/delete operations
- [ ] **Embedding Analysis Tool** - `<embedding_analysis>` for similarity detection
- [ ] **Tool Processing Pipeline** - Handle memory tools in conversation flow
- [ ] **Memory Enhancement Tool** - `<memory_enhance>` for iterative improvement

### Phase 4: AI-Assisted Memory Workflows
- [ ] **Feedback Analysis Workflows** - AI reviews and categorizes feedback
- [ ] **Memory Generalization** - AI strengthens specific feedback into general patterns
- [ ] **Synthetic Memory Creation** - Transform negative feedback into corrective memories
- [ ] **Deduplication Logic** - Prevent overlapping memories using embeddings
- [ ] **Memory Quality Assessment** - AI-assisted memory evaluation and improvement

### Phase 5: Recall Integration & Polish
- [ ] **Recall Tag Processing** - Detect `<recall>` tags in analytics conversations
- [ ] **Memory Retrieval** - Similarity search and context injection
- [ ] **Memory Usage Tracking** - Monitor which memories are being recalled
- [ ] **Performance Optimization** - Efficient embedding search and caching
- [ ] **Documentation & Testing** - Comprehensive testing and user guides

---

## Memory Management Workflows

### Conversational Memory Curation

#### Feedback Review Workflow
```
Human: "Review this week's thumbs-up feedback"

AI: <metadata_sql>
SELECT fd.description_text, fd.created_at, ml.content as message_content
FROM pet_meta.feedback_details fd 
JOIN pet_meta.message_log ml ON fd.message_id = ml.id
WHERE fd.remember_uprate = true 
AND fd.created_at > CURRENT_DATE - INTERVAL '7 days'
ORDER BY fd.created_at DESC
</metadata_sql>

AI: "I found 8 feedback items marked for remembering:
- 3 about SQL window functions (ROW_NUMBER, RANK patterns)  
- 2 about chart color customization
- 2 about data export formats
- 1 about query optimization

The SQL window functions show a clear pattern. Should I create a generalized memory?"
```

#### Memory Creation Workflow
```
Human: "Yes, create a generalized memory for SQL window functions"

AI: <embedding_analysis>
compare_to_existing: true
text: "SQL window functions ROW_NUMBER RANK PARTITION BY"
show_similar_memories: true
</embedding_analysis>

AI: "I found one similar memory (78% match) about basic SQL queries, but nothing specific to window functions.

<memory_action type="create">
source_feedback_ids: [123, 456, 789]
content: "SQL Window Functions for Ranking and Analytics

When users ask about ranking, ordering, or analytical calculations within groups, window functions are the solution:

Key Functions:
- ROW_NUMBER(): Unique sequential numbers, great for deduplication
- RANK(): Handles ties by skipping numbers (1,2,2,4)  
- DENSE_RANK(): Handles ties without skipping (1,2,2,3)
- PARTITION BY: Groups data before applying window function

Common patterns users struggle with:
- Ranking within categories: ROW_NUMBER() OVER (PARTITION BY category ORDER BY value DESC)
- Top N per group: window functions + WHERE clauses
- Running totals: SUM() OVER (PARTITION BY ... ORDER BY ...)

Remember: OVER clause is required, PARTITION BY is optional but powerful for grouping."

description: "Consolidated pattern from 3 user feedback instances about window functions"
</memory_action>

Memory created successfully! ID: 42"
```

#### Synthetic Memory from Negative Feedback
```
Human: "Review thumbs-down feedback for common mistakes"

AI: <metadata_sql>
SELECT fd.what_was_wrong, fd.what_user_wanted, 
       ml.content as ai_response,
       prev_ml.content as user_request
FROM pet_meta.feedback_details fd
JOIN pet_meta.message_log ml ON fd.message_id = ml.id
JOIN pet_meta.message_log prev_ml ON prev_ml.conversation_id = ml.conversation_id 
     AND prev_ml.id < ml.id AND prev_ml.role = 'user'
WHERE fd.feedback_type = 'thumbs_down'
ORDER BY fd.created_at DESC LIMIT 5
</metadata_sql>

AI: "I found a pattern: Users asking for 'monthly sales' but getting overly complex daily breakdowns.

<memory_action type="create_synthetic">
source_feedback_ids: [987, 988]
original_mistake: "Over-complicated time aggregation when simple monthly grouping was requested"
corrected_approach: "Time Aggregation Best Practices

When users ask for time-based summaries:

1. CLARIFY granularity first: daily/weekly/monthly/yearly
2. Start simple, don't over-engineer
3. For monthly aggregation:
   - DATE_TRUNC('month', date_col) for PostgreSQL/DuckDB
   - FORMAT(date_col, 'yyyy-MM') for SQL Server  
   - strftime('%Y-%m', date_col) for SQLite

RED FLAG: User says 'monthly' but you're thinking about daily breakdowns, date arithmetic, or complex subqueries.

GREEN FLAG: Simple GROUP BY with clear date functions and descriptive column names."

memory_type: "error_correction"
</memory_action>

Synthetic memory created to prevent this mistake pattern!"
```

## Memory Management Tools

### Core Tools for Memory Conversations

#### 1. `<metadata_sql>` - Query Metadata Database
Query feedback details, existing memories, and conversation history:
```xml
<metadata_sql>
SELECT fd.description_text, fd.remember_uprate, ml.content
FROM pet_meta.feedback_details fd
JOIN pet_meta.message_log ml ON fd.message_id = ml.id  
WHERE fd.feedback_type = 'thumbs_up' AND fd.remember_uprate = true
</metadata_sql>
```

#### 2. `<memory_action>` - Memory Operations
Create, update, or delete memories with full metadata:
```xml
<memory_action type="create">
content: "Memory content with reasoning and examples"
source_feedback_ids: [123, 456]
memory_type: "curated"
description: "Why this memory was created"
</memory_action>
```

#### 3. `<embedding_analysis>` - Similarity Detection
Prevent duplicates and find related memories:
```xml
<embedding_analysis>
text: "Query text to analyze"
compare_to_existing: true
threshold: 0.8
show_similar_memories: true
</embedding_analysis>
```

#### 4. `<memory_enhance>` - Iterative Improvement
Strengthen existing memories with new insights:
```xml
<memory_enhance memory_id="42">
improvement_type: "add_examples"
reasoning: "Recent feedback shows users also struggle with NTILE function"
enhanced_content: "Enhanced memory content..."
</memory_enhance>
```

---

## Testing Strategy

### Feedback System Tests
- **Dialog Functionality**: Test thumbs up/down dialogs with various input scenarios  
- **Context Extraction**: Verify preceding user message extraction works correctly
- **Database Operations**: Test feedback_details CRUD operations and data integrity
- **State Persistence**: Ensure dialog state persists and displays existing feedback

### Memory Management Tests
- **Tool Processing**: Test metadata_sql, memory_action, and embedding_analysis tools
- **Conversation Type Detection**: Verify "Memories:" prefix triggers memory mode
- **Memory CRUD**: Test memory creation, enhancement, and deletion workflows
- **Embedding Integration**: Test OpenAI API integration and similarity search

### AI-Assisted Workflow Tests
- **Pattern Recognition**: Test AI's ability to identify feedback patterns
- **Memory Generalization**: Verify AI can strengthen specific feedback into patterns
- **Synthetic Memory Creation**: Test conversion of negative feedback to corrective memories
- **Deduplication**: Test similarity detection and overlap prevention

### Integration Tests
- **End-to-End Workflows**: Test complete feedback → analysis → memory creation flow
- **Recall Integration**: Test `<recall>` → similarity search → `<memo>` injection
- **Cross-Conversation Recall**: Verify memories work across different analytics conversations
- **Performance with Scale**: Test system with 100+ memories and feedback items

---

## Risk Mitigation

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenAI API failures | High | Implement retry logic, graceful degradation for memory tools |
| Memory quality degradation | High | Human oversight required for all memory operations |
| Embedding storage growth | Medium | Monitor database size, implement memory pruning workflows |
| Tool complexity | Medium | Start with minimal viable tools, add features incrementally |

### Workflow Risks  
| Risk | Impact | Mitigation |
|------|--------|------------|
| Poor memory curation | High | AI-assisted analysis with human approval required |
| Memory duplication | Medium | Embedding similarity checks before creation |
| Inconsistent quality | Medium | Standardized prompts and memory enhancement workflows |
| User adoption | Low | Developer-only access initially, gradual rollout |

---

## Success Metrics

### Functional Metrics
- [ ] **Feedback Collection**: >90% of thumbs up/down clicks complete dialog workflow
- [ ] **Memory Creation**: AI successfully identifies patterns in 80%+ of feedback reviews
- [ ] **Recall Integration**: `<recall>` tags retrieve relevant memories in analytics conversations
- [ ] **Tool Reliability**: Memory management tools execute successfully 95%+ of the time

### Quality Metrics  
- [ ] **Memory Relevance**: >85% of recalled memories rated as helpful by users
- [ ] **Deduplication**: <10% of created memories flagged as duplicates
- [ ] **Synthetic Memory Value**: Corrective memories from negative feedback prevent repeat mistakes
- [ ] **Memory Enhancement**: Regular memory improvement sessions maintain quality

### Workflow Metrics
- [ ] **Curation Efficiency**: Memory curation sessions handle 20+ feedback items per hour
- [ ] **Pattern Recognition**: AI identifies actionable patterns in 60%+ of feedback batches  
- [ ] **Human Oversight**: 100% of memory operations require and receive human approval
- [ ] **Database Growth**: Sustainable growth of <50 high-quality memories per month

---

## Deployment Strategy

### Phase 1: Developer Mode Only
1. **Memory Conversations**: Enable "Memories:" conversation type in dev mode
2. **Feedback Dialogs**: Deploy enhanced thumbs up/down dialogs to all users
3. **Local Testing**: Test memory tools and workflows with development data
4. **Team Training**: Train team members on memory curation workflows

### Phase 2: Controlled Rollout  
1. **Beta Testing**: Memory management access for selected power users
2. **Quality Validation**: Monitor memory quality and recall effectiveness
3. **Workflow Refinement**: Improve prompts and tools based on usage patterns
4. **Performance Monitoring**: Track embedding generation and search performance

### Phase 3: Full Integration
1. **Production Deployment**: Enable recall integration in analytics conversations
2. **Usage Analytics**: Monitor memory recall frequency and effectiveness  
3. **Continuous Improvement**: Regular memory curation and enhancement sessions
4. **Documentation**: Comprehensive guides for memory management workflows

---

## Future Enhancements

### Short Term Improvements
- **Advanced Pattern Recognition**: AI identifies more subtle patterns across feedback
- **Memory Categories**: Tag memories by domain (SQL, visualizations, data modeling)
- **Usage Analytics**: Track which memories are most frequently recalled
- **Bulk Memory Operations**: Tools for managing multiple memories efficiently

### Medium Term Vision
- **Memory Hierarchies**: Organize memories into topic-based hierarchies  
- **Time-Based Insights**: Track how memory needs evolve over time
- **Quality Scoring**: Automated quality assessment based on recall success
- **Cross-Team Sharing**: Share curated memories across different List Pet instances

### Long Term Possibilities
- **Adaptive Learning**: Memory system learns from successful/unsuccessful recalls
- **Domain Specialization**: Separate memory sets for different analytical domains
- **Integration APIs**: Export memories for use in other AI systems
- **Collaborative Curation**: Multiple team members collaborate on memory creation

---

## Key Design Decisions

### Architectural Choices
- [x] **Conversational Interface**: Memory management through specialized chat conversations
- [x] **Human-in-the-Loop**: All memory operations require human approval
- [x] **Developer Mode Access**: Limit memory management to developer mode initially
- [ ] **Embedding Model**: Start with text-embedding-3-small, evaluate alternatives later

### Implementation Priorities  
- [x] **Quality over Automation**: High-touch curation vs automated memory creation
- [x] **AI-Assisted Workflows**: Leverage LLM capabilities for analysis and enhancement
- [x] **Incremental Complexity**: Start simple, add advanced features based on usage
- [ ] **Cost Management**: Monitor OpenAI API usage and implement budgets

---

## Conclusion

This conversational memory management system represents a significant evolution from automated queue-based approaches. By leveraging AI-assisted workflows within a conversational interface, we achieve:

### Core Benefits

**Higher Quality Memories**: Human oversight ensures every memory is valuable and well-formed, preventing the noise of automated systems.

**Natural Interaction**: Memory management feels like collaborating with an intelligent assistant rather than operating complex tools.

**Adaptive Learning**: The system can generalize specific feedback into broader patterns and create synthetic memories from mistakes.

**Sustainable Growth**: Careful curation prevents memory bloat while building a truly valuable knowledge base.

### Success Factors

The system's success relies on three key principles:

1. **AI as Assistant, Human as Curator**: The AI handles analysis and suggestions, humans make all final decisions
2. **Conversational Workflows**: Complex memory operations become natural language interactions  
3. **Quality Focus**: Better to have 50 excellent memories than 500 mediocre ones

This approach transforms memory management from a technical chore into an engaging collaborative process that continuously improves the AI's knowledge and capabilities.

---

*This design document reflects the conversational memory management approach and will be updated as implementation progresses.*
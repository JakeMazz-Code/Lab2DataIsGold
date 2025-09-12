# course_search_app.py - Complete Code
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from pathlib import Path
import re
from typing import List, Dict, Any

# Page configuration
st.set_page_config(
    page_title="Columbia SIS Documentation Search",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Columbia branding and better UI
st.markdown("""
    <style>
    /* Main header styling */
    .main-header {
        background: linear-gradient(90deg, #003865 0%, #005A9C 100%);
        color: white;
        padding: 2rem;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.1rem;
        opacity: 0.95;
    }
    
    /* Search result cards */
    .search-result {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        border-left: 4px solid #003865;
        transition: all 0.3s ease;
    }
    
    .search-result:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        transform: translateY(-2px);
    }
    
    /* Metric cards */
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
        border: 1px solid #e1e4e8;
    }
    
    /* Keyword tags */
    .keyword-tag {
        display: inline-block;
        background-color: #E3F2FD;
        padding: 3px 10px;
        border-radius: 15px;
        margin: 2px;
        font-size: 0.85rem;
        color: #1976D2;
        border: 1px solid #BBDEFB;
    }
    
    /* Category badge */
    .category-badge {
        display: inline-block;
        background-color: #003865;
        color: white;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Quick search buttons */
    .stButton > button {
        background-color: #003865;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #005A9C;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #f5f7fa;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #003865;
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #005A9C;
    }
    
    /* Info boxes */
    .info-box {
        background-color: #E3F2FD;
        border-left: 4px solid #1976D2;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
    }
    
    /* Success box */
    .success-box {
        background-color: #E8F5E9;
        border-left: 4px solid #4CAF50;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

class DocumentSearchEngine:
    """Advanced search engine for transformed documentation data"""
    
    def __init__(self, transformed_data: List[Dict]):
        self.documents = transformed_data
        self.build_search_index()
    
    def build_search_index(self):
        """Build search index for faster searching"""
        self.search_index = {}
        for i, doc in enumerate(self.documents):
            # Index by keywords
            for keyword in doc.get('keywords', []):
                if keyword not in self.search_index:
                    self.search_index[keyword] = []
                self.search_index[keyword].append(i)
    
    def search(self, query: str, category: str = None, search_type: str = "all") -> List[Dict]:
        """
        Advanced search through transformed documentation
        
        Args:
            query: Search query string
            category: Filter by specific category
            search_type: Type of search (all, title, keywords, content)
        """
        if not query:
            return []
        
        results = []
        query_terms = query.lower().split()
        
        for doc_idx, doc in enumerate(self.documents):
            score = 0
            matches = []
            
            # Apply category filter first
            if category and category != "All Categories":
                if doc.get('category') != category:
                    continue
            
            # Search based on search type
            if search_type in ["all", "title"]:
                title = doc.get('title', '').lower()
                for term in query_terms:
                    if term in title:
                        score += 10
                        matches.append(f"Title: '{term}'")
            
            if search_type in ["all", "keywords"]:
                keywords = [kw.lower() for kw in doc.get('keywords', [])]
                for term in query_terms:
                    if any(term in kw for kw in keywords):
                        score += 8
                        matches.append(f"Keyword: '{term}'")
            
            if search_type in ["all", "content"]:
                # Search in description
                description = doc.get('content', {}).get('description', '').lower()
                for term in query_terms:
                    if term in description:
                        score += 5
                        matches.append(f"Description: '{term}'")
                
                # Search in summary
                summary = doc.get('summary', '').lower()
                for term in query_terms:
                    if term in summary:
                        score += 3
                        matches.append(f"Summary: '{term}'")
            
            # Search in category name
            if query.lower() in doc.get('category', '').lower():
                score += 4
                matches.append("Category match")
            
            if score > 0:
                # Add match information to doc
                doc_with_score = doc.copy()
                doc_with_score['_search_score'] = score
                doc_with_score['_search_matches'] = matches
                results.append((score, doc_with_score))
        
        # Sort by relevance score (highest first)
        results.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in results]
    
    def get_similar_documents(self, doc_id: str, limit: int = 5) -> List[Dict]:
        """Find similar documents based on keywords"""
        target_doc = None
        for doc in self.documents:
            if doc.get('id') == doc_id:
                target_doc = doc
                break
        
        if not target_doc:
            return []
        
        target_keywords = set(target_doc.get('keywords', []))
        similarities = []
        
        for doc in self.documents:
            if doc.get('id') == doc_id:
                continue
            
            doc_keywords = set(doc.get('keywords', []))
            overlap = len(target_keywords.intersection(doc_keywords))
            
            if overlap > 0:
                similarities.append((overlap, doc))
        
        similarities.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in similarities[:limit]]

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_transformed_data():
    """Load transformed data created by the scraper"""
    data_path = Path('data/transformed_data.json')
    
    if data_path.exists():
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
            return []
    else:
        return []

@st.cache_data(ttl=300)
def load_analytics():
    """Load analytics data created by the scraper"""
    analytics_path = Path('data/analytics.json')
    
    if analytics_path.exists():
        try:
            with open(analytics_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Error loading analytics: {str(e)}")
            return {}
    return {}

def display_search_result(doc: Dict, index: int):
    """Display a single search result with rich formatting"""
    with st.expander(
        f"📄 **{doc.get('title', 'Untitled')}** | {doc.get('category', 'Unknown')}",
        expanded=(index == 0)
    ):
        # Category badge
        st.markdown(f'<span class="category-badge">{doc.get("category", "Unknown")}</span>', 
                   unsafe_allow_html=True)
        
        # Two column layout
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Summary
            if doc.get('summary'):
                st.markdown("**📝 Summary:**")
                st.info(doc['summary'])
            
            # Description
            if doc.get('content', {}).get('description'):
                st.markdown("**📖 Description:**")
                desc = doc['content']['description']
                if len(desc) > 500:
                    desc = desc[:500] + "..."
                st.write(desc)
            
            # Keywords as tags
            if doc.get('keywords'):
                st.markdown("**🏷️ Keywords:**")
                keywords_html = " ".join([
                    f'<span class="keyword-tag">{kw}</span>'
                    for kw in doc['keywords'][:10]
                ])
                st.markdown(keywords_html, unsafe_allow_html=True)
            
            # URL
            if doc.get('url'):
                st.markdown(f"**🔗 URL:** [{doc['url']}]({doc['url']})")
            
            # Search matches (if available)
            if doc.get('_search_matches'):
                st.caption(f"Matched in: {', '.join(set(doc['_search_matches']))}")
        
        with col2:
            # Metrics
            st.markdown("**📊 Document Metrics:**")
            
            metrics = doc.get('metrics', {})
            
            # Create metric cards
            st.metric("Words", f"{metrics.get('word_count', 0):,}")
            st.metric("Sections", doc.get('content', {}).get('section_count', 0))
            st.metric("Links", doc.get('navigation', {}).get('link_count', 0))
            
            # Technical indicators
            tech = doc.get('technical_indicators', {})
            if tech.get('uses_javascript'):
                st.success("✓ JavaScript")
            if tech.get('has_api_endpoints'):
                st.success("✓ API Endpoints")
            if doc.get('content', {}).get('has_code_examples'):
                st.success("✓ Code Examples")
            if doc.get('content', {}).get('has_forms'):
                st.success("✓ Forms")

def main():
    """Main application function"""
    
    # Initialize session state
    if 'search_history' not in st.session_state:
        st.session_state.search_history = []
    if 'last_search' not in st.session_state:
        st.session_state.last_search = None
    if 'view_mode' not in st.session_state:
        st.session_state.view_mode = 'grid'
    
    # Load data
    documents = load_transformed_data()
    analytics = load_analytics()
    
    # Check if data is available
    if not documents:
        st.markdown("""
            <div class="main-header">
                <h1>🎓 Columbia SIS Documentation Search</h1>
                <p>Intelligent search through scraped documentation</p>
            </div>
        """, unsafe_allow_html=True)
        
        st.error("""
        ### ⚠️ No Data Found!
        
        Please run your scraper first to generate data:
```bash
        python src/scraper.py
This will create the required files:
    - `data/transformed_data.json`
    - `data/analytics.json`
    
    After running the scraper, refresh this page.
    """)
    
        if st.button("🔄 Refresh Page"):
            st.cache_data.clear()
            st.rerun()
        
        return
    
    # Initialize search engine
    search_engine = DocumentSearchEngine(documents)

    # Sidebar
    with st.sidebar:
        st.markdown("## 📊 Documentation Overview")
    
        # Display metrics
        if analytics:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Pages", f"{analytics.get('total_pages', 0):,}")
            with col2:
                avg_words = analytics.get('avg_metrics', {}).get('word_count', 0)
                st.metric("Avg Words", f"{avg_words:.0f}")
        
            # Category distribution
            st.markdown("### 📁 Categories")
            categories = analytics.get('categories', {})
            if categories:
                # Sort categories by count
                sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
                for cat, count in sorted_cats[:6]:
                    progress = count / max(categories.values())
                    st.progress(progress)
                    st.caption(f"{cat}: {count} pages")
            
                if len(sorted_cats) > 6:
                    st.caption(f"...and {len(sorted_cats) - 6} more categories")
        
            # Top keywords
            st.markdown("### 🔤 Top Keywords")
            keywords = analytics.get('top_keywords', [])[:12]
            if keywords:
                # Create two columns for keywords
                kw_cols = st.columns(2)
                for i, kw in enumerate(keywords):
                    with kw_cols[i % 2]:
                        st.caption(f"• {kw}")
        
            # Content distribution
            st.markdown("### 📈 Content Features")
            content_dist = analytics.get('content_distribution', {})
            if content_dist:
                st.info(f"📝 Forms: {content_dist.get('pages_with_forms', 0)} pages")
                st.info(f"📊 Tables: {content_dist.get('pages_with_tables', 0)} pages")
                st.info(f"💻 Code: {content_dist.get('pages_with_code', 0)} pages")
    
        # Data management
        st.markdown("---")
        st.markdown("### 🔧 Data Management")
    
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh Data", use_container_width=True):
                st.cache_data.clear()
                st.success("Cache cleared!")
                st.rerun()
    
        with col2:
            if st.button("📜 Clear History", use_container_width=True):
                st.session_state.search_history = []
                st.success("History cleared!")
    
        # Last update time
        if Path('data/transformed_data.json').exists():
            mod_time = datetime.fromtimestamp(Path('data/transformed_data.json').stat().st_mtime)
            st.caption(f"Last updated: {mod_time.strftime('%Y-%m-%d %H:%M')}")

    # Main header
    st.markdown("""
        <div class="main-header">
            <h1>🎓 Columbia SIS Documentation Search</h1>
            <p>Search through {} scraped documentation pages</p>
        </div>
    """.format(len(documents)), unsafe_allow_html=True)

    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔍 Search", 
        "📊 Analytics", 
        "📁 Browse All", 
        "📜 Search History",
        "🎯 Demo Mode"
    ])

    with tab1:
        # Quick search buttons
        st.markdown("### 🚀 Quick Searches")
    
        quick_searches = [
            "API", "registration", "authentication", 
            "student", "security", "guide", "admin", "integration"
        ]
    
        cols = st.columns(len(quick_searches) // 2)
        selected_quick = None
    
        for i, term in enumerate(quick_searches[:4]):
            with cols[i]:
                if st.button(term, key=f"quick_{term}", use_container_width=True):
                    selected_quick = term
    
        cols2 = st.columns(len(quick_searches) // 2)
        for i, term in enumerate(quick_searches[4:]):
            with cols2[i]:
                if st.button(term, key=f"quick2_{term}", use_container_width=True):
                    selected_quick = term
    
        st.markdown("---")
    
        # Main search interface
        st.markdown("### 🔎 Advanced Search")
    
        col1, col2 = st.columns([3, 1])
    
        with col1:
            search_query = st.text_input(
                "Enter search terms",
                value=selected_quick if selected_quick else "",
                placeholder="e.g., 'registration process', 'API endpoints', 'user authentication'",
                key="main_search_input"
            )
    
        with col2:
            search_type = st.selectbox(
                "Search in",
                ["all", "title", "keywords", "content"],
                format_func=lambda x: x.capitalize()
            )
    
        # Category filter
        col3, col4, col5 = st.columns([2, 2, 1])
    
        with col3:
            all_categories = ["All Categories"] + sorted(list(set(
                doc.get('category', 'Unknown') for doc in documents
            )))
            selected_category = st.selectbox(
                "Filter by category",
                all_categories
            )
    
        with col4:
            results_per_page = st.select_slider(
                "Results per page",
                options=[5, 10, 20, 50],
                value=10
            )
    
        with col5:
            search_button = st.button(
                "🔍 Search",
                type="primary",
                use_container_width=True
            )
    
        # Perform search
        if search_button or search_query or selected_quick:
            query = search_query or selected_quick
        
            if query:
                with st.spinner(f"Searching for '{query}'..."):
                    results = search_engine.search(
                        query,
                        selected_category,
                        search_type
                    )
            
                # Update search history
                if query != st.session_state.last_search:
                    st.session_state.search_history.insert(0, {
                        'query': query,
                        'category': selected_category,
                        'type': search_type,
                        'results': len(results),
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    st.session_state.last_search = query
                
                    # Keep only last 20 searches
                    st.session_state.search_history = st.session_state.search_history[:20]
            
                # Display results
                if results:
                    st.success(f"✅ Found {len(results)} result(s) for **'{query}'**")
                
                    # Results summary
                    if len(results) > results_per_page:
                        st.info(f"Showing top {results_per_page} of {len(results)} results. "
                               f"Adjust 'Results per page' to see more.")
                
                    # Display each result
                    for i, doc in enumerate(results[:results_per_page]):
                        display_search_result(doc, i)
                
                    # Export results
                    st.markdown("---")
                    if st.button("📥 Export Search Results to CSV"):
                        export_data = []
                        for doc in results:
                            export_data.append({
                                'Title': doc.get('title', ''),
                                'Category': doc.get('category', ''),
                                'URL': doc.get('url', ''),
                                'Keywords': ', '.join(doc.get('keywords', [])[:5]),
                                'Word Count': doc.get('metrics', {}).get('word_count', 0),
                                'Summary': doc.get('summary', '')[:200]
                            })
                    
                        df = pd.DataFrame(export_data)
                        csv = df.to_csv(index=False)
                    
                        st.download_button(
                            label="💾 Download CSV",
                            data=csv,
                            file_name=f"search_results_{query.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
            
                else:
                    st.warning(f"""
                    😔 No results found for **'{query}'**
                
                    **Try:**
                    - Using different keywords
                    - Checking the Browse tab to see available content
                    - Using broader search terms
                    - Selecting 'All Categories' filter
                    """)

    with tab2:
        st.markdown("## 📊 Documentation Analytics Dashboard")
    
        if analytics:
            # Summary metrics row
            st.markdown("### 📈 Summary Metrics")
            metric_cols = st.columns(5)
        
            with metric_cols[0]:
                st.metric(
                    "Total Pages",
                    f"{analytics.get('total_pages', 0):,}",
                    help="Total number of documentation pages scraped"
                )
        
            with metric_cols[1]:
                avg_words = analytics.get('avg_metrics', {}).get('word_count', 0)
                st.metric(
                    "Avg Words/Page",
                    f"{avg_words:.0f}",
                    help="Average number of words per documentation page"
                )
        
            with metric_cols[2]:
                content_dist = analytics.get('content_distribution', {})
                st.metric(
                    "Pages with Code",
                    content_dist.get('pages_with_code', 0),
                    help="Number of pages containing code examples"
                )
        
            with metric_cols[3]:
                st.metric(
                    "Pages with Forms",
                    content_dist.get('pages_with_forms', 0),
                    help="Number of pages containing forms"
                )
        
            with metric_cols[4]:
                st.metric(
                    "Avg Sections",
                    f"{content_dist.get('avg_sections_per_page', 0):.1f}",
                    help="Average number of sections per page"
                )
        
            st.markdown("---")
        
            # Visualizations
            col1, col2 = st.columns(2)
        
            with col1:
                st.markdown("### 📊 Category Distribution")
                categories_df = pd.DataFrame(
                    list(analytics.get('categories', {}).items()),
                    columns=['Category', 'Pages']
                )
                if not categories_df.empty:
                    categories_df = categories_df.sort_values('Pages', ascending=True)
                    st.bar_chart(
                        categories_df.set_index('Category')['Pages'],
                        height=400
                    )
        
            with col2:
                st.markdown("### 📏 Content Metrics")
                metrics_data = analytics.get('avg_metrics', {})
                if metrics_data:
                    # Format metric names
                    formatted_metrics = {}
                    for key, value in metrics_data.items():
                        formatted_key = key.replace('_', ' ').title()
                        formatted_metrics[formatted_key] = round(value, 2)
                
                    metrics_df = pd.DataFrame(
                        list(formatted_metrics.items()),
                        columns=['Metric', 'Average Value']
                    )
                    st.dataframe(
                        metrics_df,
                        hide_index=True,
                        use_container_width=True,
                        height=400
                    )
        
            # Technical analysis
            st.markdown("---")
            st.markdown("### 🔧 Technical Analysis")
        
            tech_summary = analytics.get('technical_summary', {})
            if tech_summary:
                tech_cols = st.columns(4)
            
                with tech_cols[0]:
                    st.info(f"""
                    **JavaScript Pages**  
                    {tech_summary.get('pages_using_javascript', 0)} pages
                    """)
            
                with tech_cols[1]:
                    st.info(f"""
                    **API Endpoints**  
                    {tech_summary.get('pages_with_api_endpoints', 0)} pages
                    """)
            
                with tech_cols[2]:
                    frameworks = tech_summary.get('frameworks_detected', {})
                    st.info(f"""
                    **Frameworks**  
                    {len(frameworks)} detected
                    """)
            
                with tech_cols[3]:
                    total_diagrams = sum(
                        doc.get('technical_indicators', {}).get('diagram_count', 0)
                        for doc in documents
                    )
                    st.info(f"""
                    **Diagrams**  
                    {total_diagrams} total
                    """)
        
            # Keyword cloud
            st.markdown("---")
            st.markdown("### 🔤 Top 20 Keywords")
        
            top_keywords = analytics.get('top_keywords', [])[:20]
            if top_keywords:
                # Create keyword frequency visualization
                keyword_freq = analytics.get('keyword_frequency', {})
                keyword_data = []
                for kw in top_keywords:
                    if kw in keyword_freq:
                        keyword_data.append({'Keyword': kw, 'Frequency': keyword_freq[kw]})
            
                if keyword_data:
                    kw_df = pd.DataFrame(keyword_data)
                    st.bar_chart(
                        kw_df.set_index('Keyword')['Frequency'],
                        height=300
                    )

    with tab3:
        st.markdown("## 📁 Browse All Documentation")
    
        # View mode selector
        col1, col2 = st.columns([3, 1])
        with col2:
            view_mode = st.radio(
                "View mode",
                ["Table", "Cards"],
                horizontal=True
            )
    
        # Filters
        st.markdown("### 🔍 Filters")
        filter_cols = st.columns(4)
    
        with filter_cols[0]:
            category_filter = st.multiselect(
                "Categories",
                sorted(list(set(doc.get('category', 'Unknown') for doc in documents)))
            )
    
        with filter_cols[1]:
            min_words = st.number_input(
                "Min word count",
                min_value=0,
                max_value=10000,
                value=0,
                step=100
            )
    
        with filter_cols[2]:
            has_code = st.checkbox("Has code examples")
            has_forms = st.checkbox("Has forms")
    
        with filter_cols[3]:
            keyword_filter = st.text_input(
                "Keyword filter",
                placeholder="Filter by keyword"
            )
    
        # Apply filters
        filtered_docs = documents.copy()
    
        if category_filter:
            filtered_docs = [d for d in filtered_docs if d.get('category') in category_filter]
    
        if min_words > 0:
            filtered_docs = [d for d in filtered_docs 
                           if d.get('metrics', {}).get('word_count', 0) >= min_words]
    
        if has_code:
            filtered_docs = [d for d in filtered_docs 
                           if d.get('content', {}).get('has_code_examples')]
    
        if has_forms:
            filtered_docs = [d for d in filtered_docs 
                           if d.get('content', {}).get('has_forms')]
    
        if keyword_filter:
            filtered_docs = [d for d in filtered_docs 
                           if any(keyword_filter.lower() in kw.lower() 
                                 for kw in d.get('keywords', []))]
    
        st.info(f"Showing {len(filtered_docs)} of {len(documents)} documents")
    
        if view_mode == "Table":
            # Table view
            if filtered_docs:
                # Create DataFrame
                table_data = []
                for doc in filtered_docs:
                    table_data.append({
                        'Title': doc.get('title', 'Untitled')[:60],
                        'Category': doc.get('category', 'Unknown'),
                        'Words': doc.get('metrics', {}).get('word_count', 0),
                        'Sections': doc.get('content', {}).get('section_count', 0),
                        'Links': doc.get('navigation', {}).get('link_count', 0),
                        'Code': '✓' if doc.get('content', {}).get('has_code_examples') else '',
                        'Forms': '✓' if doc.get('content', {}).get('has_forms') else '',
                        'Keywords': ', '.join(doc.get('keywords', [])[:3])
                    })
            
                df = pd.DataFrame(table_data)
            
                # Display with sorting
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    height=600
                )
            
                # Export button
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Export Filtered Data to CSV",
                    csv,
                    f"documentation_filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv"
                )
    
        else:
            # Card view
            if filtered_docs:
                # Pagination for card view
                items_per_page = 12
                total_pages = (len(filtered_docs) - 1) // items_per_page + 1
            
                page = st.number_input(
                    "Page",
                    min_value=1,
                    max_value=total_pages,
                    value=1
                )
            
                start_idx = (page - 1) * items_per_page
                end_idx = min(start_idx + items_per_page, len(filtered_docs))
            
                # Display cards in grid
                cols = st.columns(3)
                for i, doc in enumerate(filtered_docs[start_idx:end_idx]):
                    with cols[i % 3]:
                        st.markdown(f"""
                        <div class="search-result">
                            <h4>{doc.get('title', 'Untitled')[:50]}</h4>
                            <span class="category-badge">{doc.get('category', 'Unknown')}</span>
                            <p style="margin-top: 10px; color: #666; font-size: 0.9rem;">
                                {doc.get('summary', 'No summary available')[:100]}...
                            </p>
                            <div style="margin-top: 10px;">
                                <small>📝 {doc.get('metrics', {}).get('word_count', 0)} words</small> |
                                <small>🔗 {doc.get('navigation', {}).get('link_count', 0)} links</small>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

    with tab4:
        st.markdown("## 📜 Search History")
    
        if st.session_state.search_history:
            st.info(f"Showing last {len(st.session_state.search_history)} searches")
        
            # Create DataFrame from history
            history_df = pd.DataFrame(st.session_state.search_history)
        
            # Display with clickable queries
            for idx, row in history_df.iterrows():
                col1, col2, col3, col4, col5 = st.columns([3, 2, 1, 1, 2])
            
                with col1:
                    if st.button(f"🔍 {row['query']}", key=f"history_{idx}"):
                        st.session_state.last_search = row['query']
                        st.rerun()
            
                with col2:
                    st.text(row['category'])
            
                with col3:
                    st.text(row['type'].capitalize())
            
                with col4:
                    st.text(f"{row['results']} results")
            
                with col5:
                    st.text(row['timestamp'].split()[1][:5])  # Show time only
        
            # Export history
            if st.button("📥 Export Search History"):
                csv = history_df.to_csv(index=False)
                st.download_button(
                    "💾 Download History CSV",
                    csv,
                    f"search_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv"
                )
        else:
            st.info("No search history yet. Start searching to build your history!")

    with tab5:
        st.markdown("## 🎯 Demo Mode")
        st.info("""
        This demo mode is designed for your class presentation. 
        Click the button below to run an automated demo sequence.
        """)
    
        if st.button("▶️ Start Demo Sequence", type="primary"):
            # Demo sequence
            demo_searches = [
                ("API", "Searching for API documentation..."),
                ("registration", "Finding registration guides..."),
                ("authentication", "Looking up authentication methods..."),
                ("student records", "Searching student record documentation...")
            ]
        
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()
        
            for i, (query, message) in enumerate(demo_searches):
                progress = (i + 1) / len(demo_searches)
                progress_bar.progress(progress)
                status_text.text(message)
            
                # Perform search
                results = search_engine.search(query)
            
                # Display results summary
                with results_container:
                    st.success(f"✅ **{query}**: Found {len(results)} results")
                
                    if results and i == 0:  # Show details for first search only
                        st.markdown("**Sample result:**")
                        doc = results[0]
                        st.markdown(f"""
                        - **Title:** {doc.get('title', 'Untitled')}
                        - **Category:** {doc.get('category', 'Unknown')}
                        - **Keywords:** {', '.join(doc.get('keywords', [])[:5])}
                        """)
            
                # Pause for effect
                import time
                time.sleep(1.5)
        
            progress_bar.progress(1.0)
            status_text.text("✅ Demo complete!")
        
            st.balloons()
        
            st.markdown("""
            ### Demo Summary
        
            The search system successfully demonstrated:
            1. ✅ Natural language search capabilities
            2. ✅ Category-based filtering
            3. ✅ Relevance scoring
            4. ✅ Rich metadata extraction
            5. ✅ Export functionality
        
            **Ready for live demonstration!**
            """)

if __name__ == "__main__":
    main()
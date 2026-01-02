import streamlit as st
import pandas as pd
import time
from datetime import datetime

# ================= CONFIG =================
PER_QUESTION_TIME = 30  # seconds per question
CSV_FILE_PATH = r"TASK_STATUS - Sheet15(3).csv"

# ================= STYLING =================
def apply_custom_css():
    st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        font-weight: 500;
    }
    .question-card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .question-card h4 {
        color: white !important;
        background-color: #2c3e50;
        padding: 15px;
        border-radius: 8px;
    }
    .timer-critical {
        color: #dc3545;
        font-weight: bold;
        font-size: 1.2em;
    }
    .timer-warning {
        color: #fd7e14;
        font-weight: bold;
        font-size: 1.2em;
    }
    .timer-normal {
        color: #28a745;
        font-weight: bold;
        font-size: 1.2em;
    }
    </style>
    """, unsafe_allow_html=True)

# ================= DATA LOADING =================
def load_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip().str.lower()
        
        # Validate required columns
        required_cols = ['question', 'answer']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
            st.info("📋 Required format: question, option1, option2, option3, option4, [option5], answer")
            return None
        
        # Check for at least 2 options
        option_cols = [col for col in df.columns if col.startswith('option')]
        if len(option_cols) < 2:
            st.error("❌ At least 2 option columns are required")
            return None
        
        # Remove empty questions
        df = df.dropna(subset=['question', 'answer'])
        
        if len(df) == 0:
            st.error("❌ No valid questions found in the CSV file")
            return None
            
        return df
    except FileNotFoundError:
        st.error(f"❌ File not found: {file_path}")
        return None
    except Exception as e:
        st.error(f"❌ Error loading CSV: {str(e)}")
        return None

def shuffle_questions(df):
    return df.sample(frac=1).reset_index(drop=True)

# ================= SESSION INIT =================
def init_session(df, time_limit):
    st.session_state.df = df
    st.session_state.q_index = 0
    st.session_state.answers = {}
    st.session_state.flagged = set()
    st.session_state.start_time = time.time()
    st.session_state.total_time = time_limit
    st.session_state.finished = False
    st.session_state.started = True
    st.session_state.exam_submitted = False
    st.session_state.visit_count = {i: 0 for i in range(len(df))}

# ================= TIME =================
def time_left():
    elapsed = time.time() - st.session_state.start_time
    return max(0, int(st.session_state.total_time - elapsed))

def format_time(seconds):
    mins, secs = divmod(seconds, 60)
    return f"{int(mins):02d}:{int(secs):02d}"

def show_timer():
    t = time_left()
    
    if t <= 0:
        st.session_state.finished = True
        st.session_state.exam_submitted = True
        st.rerun()
    
    # Color coding based on time left
    if t <= 60:
        timer_class = "timer-critical"
        icon = "🚨"
    elif t <= 300:
        timer_class = "timer-warning"
        icon = "⚠️"
    else:
        timer_class = "timer-normal"
        icon = "⏱️"
    
    st.markdown(f"""
    <div style='text-align: center; padding: 15px; background-color: #f0f2f6; border-radius: 10px;'>
        <span class='{timer_class}'>{icon} Time Remaining: {format_time(t)}</span>
    </div>
    """, unsafe_allow_html=True)

# ================= UI HELPERS =================
def show_progress(idx, total):
    answered = len(st.session_state.answers)
    unanswered = total - answered
    flagged = len(st.session_state.flagged)
    
    progress = (idx + 1) / total
    st.progress(progress)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Question", f"{idx + 1}/{total}")
    with col2:
        st.metric("Answered", answered, delta=None)
    with col3:
        st.metric("Unanswered", unanswered, delta=None)
    with col4:
        st.metric("Flagged", flagged, delta=None)

def show_question(row, idx):
    # Track visits
    st.session_state.visit_count[idx] += 1
    
    # Question header with flag
    col1, col2 = st.columns([6, 1])
    with col1:
        st.markdown(f"### Question {idx + 1}")
    with col2:
        is_flagged = idx in st.session_state.flagged
        if st.button("🚩" if is_flagged else "⚐", key=f"flag_{idx}", help="Flag for review"):
            if is_flagged:
                st.session_state.flagged.discard(idx)
            else:
                st.session_state.flagged.add(idx)
            st.rerun()
    
    st.markdown(f"<div class='question-card'><h4>{row['question']}</h4></div>", unsafe_allow_html=True)
    
    # Dynamically detect available options
    options = {}
    option_labels = ['A', 'B', 'C', 'D', 'E', 'F']
    option_num = 1
    
    while f'option{option_num}' in row.index:
        option_value = row[f'option{option_num}']
        if pd.notna(option_value) and str(option_value).strip():
            options[option_labels[option_num - 1]] = str(option_value).strip()
        option_num += 1
    
    # Show current answer if exists
    current_answer = st.session_state.answers.get(idx)
    default_index = list(options.keys()).index(current_answer) if current_answer in options else None
    
    selected = st.radio(
        "Select your answer:",
        options.keys(),
        format_func=lambda x: f"{x}. {options[x]}",
        index=default_index,
        key=f"q_{idx}"
    )
    
    st.session_state.answers[idx] = selected

def show_question_palette(df):
    st.sidebar.markdown("### Question Navigator")
    st.sidebar.markdown("---")
    
    # Legend
    st.sidebar.markdown("**Legend:**")
    st.sidebar.markdown("🟢 Answered | ⚪ Not Answered | 🚩 Flagged")
    st.sidebar.markdown("---")
    
    # Question grid
    cols_per_row = 5
    for i in range(0, len(df), cols_per_row):
        cols = st.sidebar.columns(cols_per_row)
        for j, col in enumerate(cols):
            q_idx = i + j
            if q_idx >= len(df):
                break
            
            # Determine button style
            if q_idx in st.session_state.flagged:
                icon = "🚩"
            elif q_idx in st.session_state.answers:
                icon = "🟢"
            else:
                icon = "⚪"
            
            is_current = q_idx == st.session_state.q_index
            label = f"**{q_idx + 1}**" if is_current else str(q_idx + 1)
            
            if col.button(f"{icon} {label}", key=f"nav_{q_idx}", use_container_width=True):
                st.session_state.q_index = q_idx
                st.rerun()

def show_submit_confirmation():
    st.warning("⚠️ You are about to submit your exam. This action cannot be undone.")
    
    total = len(st.session_state.df)
    answered = len(st.session_state.answers)
    unanswered = total - answered
    
    if unanswered > 0:
        st.error(f"❗ You have {unanswered} unanswered question(s).")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Yes, Submit", type="primary", use_container_width=True):
            st.session_state.finished = True
            st.session_state.exam_submitted = True
            st.rerun()
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.show_submit_modal = False
            st.rerun()

# ================= RESULT =================
def show_result(df):
    st.balloons()
    
    score = 0
    correct_answers = []
    wrong_answers = []
    
    for i, row in df.iterrows():
        user_ans = st.session_state.answers.get(i)
        correct_ans = row["answer"].strip().upper()
        
        if user_ans == correct_ans:
            score += 1
            correct_answers.append(i)
        else:
            wrong_answers.append(i)
    
    total = len(df)
    percentage = (score / total) * 100
    
    # Summary Card
    st.markdown("## 🎓 Exam Results")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Score", f"{score}/{total}")
    with col2:
        st.metric("Percentage", f"{percentage:.1f}%")
    with col3:
        st.metric("Correct", score)
    with col4:
        st.metric("Wrong", len(wrong_answers))
    
    # Performance indicator
    if percentage >= 90:
        st.success("🌟 Outstanding! Excellent performance!")
    elif percentage >= 75:
        st.success("👍 Great job! Well done!")
    elif percentage >= 60:
        st.info("👌 Good effort! Keep practicing!")
    else:
        st.warning("📚 Keep studying! You can do better!")
    
    st.markdown("---")
    
    # Detailed Review
    tab1, tab2, tab3 = st.tabs(["📊 Summary", "✅ Correct Answers", "❌ Wrong Answers"])
    
    with tab1:
        st.markdown("### Performance Summary")
        time_taken = st.session_state.total_time - time_left()
        st.write(f"**Time Taken:** {format_time(time_taken)}")
        st.write(f"**Questions Attempted:** {len(st.session_state.answers)}/{total}")
        st.write(f"**Questions Skipped:** {total - len(st.session_state.answers)}")
    
    with tab2:
        if correct_answers:
            st.success(f"✅ You answered {len(correct_answers)} question(s) correctly!")
            for i in correct_answers:
                row = df.iloc[i]
                with st.expander(f"Q{i + 1}: {row['question'][:60]}..."):
                    st.write(f"**Question:** {row['question']}")
                    st.write(f"**Your Answer:** {st.session_state.answers.get(i)}")
                    st.write(f"**Correct Answer:** {row['answer']}")
        else:
            st.info("No correct answers")
    
    with tab3:
        if wrong_answers:
            st.error(f"❌ Review {len(wrong_answers)} incorrect answer(s)")
            for i in wrong_answers:
                row = df.iloc[i]
                with st.expander(f"Q{i + 1}: {row['question'][:60]}..."):
                    st.write(f"**Question:** {row['question']}")
                    st.write(f"**Your Answer:** {st.session_state.answers.get(i, 'Not Answered')}")
                    st.write(f"**Correct Answer:** {row['answer']}")
                    st.markdown("**Options:**")
                    
                    # Show all available options
                    option_labels = ['A', 'B', 'C', 'D', 'E', 'F']
                    option_num = 1
                    while f'option{option_num}' in row.index:
                        option_value = row[f'option{option_num}']
                        if pd.notna(option_value) and str(option_value).strip():
                            st.write(f"{option_labels[option_num - 1]}. {option_value}")
                        option_num += 1
        else:
            st.success("Perfect score! No wrong answers!")
    
    st.markdown("---")
    if st.button("🔄 Take Another Test", type="primary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ================= MAIN =================
def main():
    st.set_page_config(page_title="MCQ Exam Practice", page_icon="📝", layout="wide")
    apply_custom_css()
    
    st.title("📝 MCQ Exam Practice Platform")
    
    # Load CSV from hardcoded path
    if "started" not in st.session_state:
        st.markdown("### Welcome to the Exam Platform")
        st.info("Loading questions from the configured file...")
        
        df = load_csv(CSV_FILE_PATH)
        
        if df is not None:
            st.success(f"✅ Successfully loaded {len(df)} questions!")
            
            # Exam configuration
            st.markdown("### 📋 Exam Configuration")
            col1, col2 = st.columns(2)
            
            with col1:
                shuffle = st.checkbox("🔀 Shuffle Questions", value=True)
                show_timer_option = st.checkbox("⏱️ Enable Timer", value=True)
            
            with col2:
                if show_timer_option:
                    time_per_q = st.number_input(
                        "Time per question (seconds)", 
                        min_value=10, 
                        max_value=300, 
                        value=30
                    )
                    total_time = len(df) * time_per_q
                    st.info(f"Total exam time: {format_time(total_time)}")
                else:
                    total_time = 999999  # Unlimited time
            
            st.markdown("---")
            
            if st.button("🚀 Start Exam", type="primary", use_container_width=True):
                processed_df = shuffle_questions(df) if shuffle else df
                init_session(processed_df, total_time)
                st.rerun()
        else:
            st.error("Failed to load the CSV file. Please check the file path and format.")
        return
    
    # Show result page
    if st.session_state.finished:
        show_result(st.session_state.df)
        return
    
    # Exam in progress
    df = st.session_state.df
    idx = st.session_state.q_index
    
    # Sidebar navigation
    show_question_palette(df)
    
    # Main content
    show_timer()
    st.markdown("---")
    show_progress(idx, len(df))
    st.markdown("---")
    
    show_question(df.iloc[idx], idx)
    
    st.markdown("---")
    
    # Navigation buttons
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        if idx > 0:
            if st.button("⬅️ Previous", use_container_width=True):
                st.session_state.q_index -= 1
                st.rerun()
    
    with col2:
        if st.button("💾 Save & Next", type="primary", use_container_width=True):
            if idx < len(df) - 1:
                st.session_state.q_index += 1
                st.rerun()
    
    with col3:
        if idx < len(df) - 1:
            if st.button("Skip ⏭️", use_container_width=True):
                st.session_state.q_index += 1
                st.rerun()
    
    with col4:
        if st.button("✅ Submit Exam", use_container_width=True):
            st.session_state.show_submit_modal = True
            st.rerun()
    
    # Submit confirmation modal
    if st.session_state.get("show_submit_modal", False):
        st.markdown("---")
        show_submit_confirmation()

if __name__ == "__main__":
    main()

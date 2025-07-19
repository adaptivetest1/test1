import streamlit as st
import pandas as pd
import plotly.express as px
import random
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import numpy as np

# ==============================================================================
# 0. General Settings and Constants
# ==============================================================================
GOOGLE_SHEET_ID = "1dzXIAD7xYUX_QM37flfqQTetaui-vycwANgvIzsOoaY"
MAX_QUESTIONS = 15
CHOICES = ["لا أوافق إطلاقًا", "أوافق إلى حد ما", "أوافق", "أوافق بشدة"]
CHOICE_VALUES = [1, 2, 3, 4]

# Trait Definitions
TRAITS = [
    "الانبساط (ذاتي)",
    "العصبية (ذاتي)",
    "التوافق (ذاتي)",
    "الضمير (ذاتي)",
    "الانفتاح (ذاتي)"
]

TRAIT_DESCRIPTIONS = {
    "الانبساط (ذاتي)": "يقيس الانبساط مدى تفاعلك مع العالم الخارجي. الأشخاص ذوو الدرجات العالية يميلون إلى أن يكونوا اجتماعيين ونشيطين ومتحمسين.",
    "العصبية (ذاتي)": "تشير العصبية إلى مدى استقرارك العاطفي. الأشخاص ذوو الدرجات العالية قد يكونون أكثر عرضة للقلق والتقلبات المزاجية.",
    "التوافق (ذاتي)": "يعكس التوافق مدى ميلك للتعاون والتعاطف. الأشخاص ذوو الدرجات العالية يكونون عادةً طيبين ومتعاونين وجديرين بالثقة.",
    "الضمير (ذاتي)": "يقيس الضمير مدى تنظيمك ومسؤوليتك. الأشخاص ذوو الدرجات العالية يتميزون بالاجتهاد والانضباط والتخطيط.",
    "الانفتاح (ذاتي)": "يشير الانفتاح إلى مدى اهتمامك بالتجارب الجديدة والأفكار الإبداعية. الأشخاص ذوو الدرجات العالية فضوليون ومبتكرون ومتقبلون للتغيير."
}

TRAIT_COLORS = {
    "الانبساط (ذاتي)": '#FFD700',
    "العصبية (ذاتي)": '#FF6347',
    "التوافق (ذاتي)": '#3CB371',
    "الضمير (ذاتي)": '#4169E1',
    "الانفتاح (ذاتي)": '#9370DB'
}

# ==============================================================================
# 1. Data Management and External Services Functions
# ==============================================================================
_sheets_client = None

@st.cache_resource
def get_google_sheets_client():
    global _sheets_client
    if _sheets_client is not None:
        return _sheets_client
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        # Load credentials from Streamlit secrets
        creds = Credentials.from_service_account_info(
            st.secrets["gcp"],
            scopes=scope
        )
        client = gspread.authorize(creds)
        _sheets_client = client
        return client
    except Exception as e:
        st.error(f"❌ خطأ أثناء الاتصال بـ Google Sheets: {e}")
        return None

def setup_google_sheet(sheet_id):
    client = get_google_sheets_client()
    if not client:
        return None
    try:
        sheet = client.open_by_key(sheet_id).sheet1
        if not sheet.get_all_values():
            headers = ['Timestamp', 'الاسم', 'السن', 'العنوان', 'السمة الأساسية'] + [f"درجة {trait}" for trait in TRAITS] + ["الدرجة العليا"]
            sheet.append_row(headers)
        return sheet
    except Exception as e:
        st.error(f"❌ خطأ في فتح أو إعداد Google Sheet: {e}")
        return None

def save_results_to_gsheets(user_data, results, dominant_trait):
    sheet = setup_google_sheet(GOOGLE_SHEET_ID)
    if not sheet:
        return False
    try:
        max_score = max(results.values()) if results else 0.0
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_data.get('name', 'N/A'),
            user_data.get('age', 'N/A'),
            user_data.get('location', 'N/A'),
            dominant_trait
        ] + [f"{results.get(trait, 0.0):.2f}" for trait in TRAITS] + [f"{max_score:.2f}"]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"❌ فشل في حفظ النتائج: {e}")
        return False

@st.cache_data
def load_questions_data(file_path="edit.xlsx"):
    try:
        df = pd.read_excel(file_path)
        df = df[df["generated_question"].notnull()]
        if "السمة" not in df.columns:
            raise ValueError("ملف الأسئلة يجب أن يحتوي على عمود 'السمة'.")
        if 'a' not in df.columns:
            df['a'] = 1.0
        if 'b' not in df.columns:
            df['b'] = 0.0
        if 'c' not in df.columns:
            df['c'] = 0.0
        if 'd' not in df.columns:
            df['d'] = 0.0
        return df
    except FileNotFoundError:
        st.error(f"❌ ملف '{file_path}' غير موجود.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ خطأ أثناء تحميل الأسئلة: {e}")
        return pd.DataFrame()

def get_next_question_logic(questions_df, session_state):
    asked_ids = session_state.get("asked_ids", set())
    last_trait = session_state.get("last_question_trait")
    last_score = session_state.get("last_score")
    remaining_questions = questions_df[~questions_df.index.isin(asked_ids)]
    if remaining_questions.empty:
        return None, "تم الانتهاء من جميع الأسئلة المتاحة."
    q = None
    if session_state["question_count"] == 0:
        q = remaining_questions.sample(1).iloc[0]
    else:
        if last_score in [2, 3] and last_trait:
            trait_specific_remaining = remaining_questions[remaining_questions["السمة"] == last_trait]
            if not trait_specific_remaining.empty:
                q = trait_specific_remaining.sample(1).iloc[0]
        if q is None:
            answered_traits_keys = session_state.get("answered_traits", {}).keys()
            new_trait_questions = remaining_questions[~remaining_questions["السمة"].isin(answered_traits_keys)]
            if not new_trait_questions.empty:
                q = new_trait_questions.sample(1).iloc[0]
            else:
                q = remaining_questions.sample(1).iloc[0]
    if q is None:
        q = remaining_questions.sample(1).iloc[0]
    session_state["current_question_id"] = q.name
    session_state["current_question_text"] = q["generated_question"]
    session_state["current_question_trait"] = q["السمة"]
    session_state["asked_ids"].add(q.name)
    return q["generated_question"], None

# ==============================================================================
# 2. Report Generation Functions
# ==============================================================================
def calculate_results(answered_traits, user_info):
    trait_scores = {}
    for trait, scores in answered_traits.items():
        trait_scores[trait] = sum(scores) / len(scores) if scores else 0.0
    dominant_trait = max(trait_scores, key=trait_scores.get) if trait_scores else "غير محدد"
    dominant_score = trait_scores.get(dominant_trait, 0.0)
    summary_for_save = {
        "name": user_info.get("name", ""),
        "age": user_info.get("age", ""),
        "location": user_info.get("location", ""),
        "test_date": user_info.get("test_date", "")
    }
    for trait in TRAITS:
        summary_for_save[f"درجة {trait}"] = round(trait_scores.get(trait, 0.0), 2)
    return trait_scores, dominant_trait, dominant_score, summary_for_save

def generate_report(results, traits, trait_colors, user_info):
    df = pd.DataFrame({
        'السمة': [trait.replace(" (ذاتي)", "") for trait in traits],
        'الدرجة': [results.get(trait, 0.0) for trait in traits]
    })
    fig = px.bar(
        df,
        x='السمة',
        y='الدرجة',
        title=f'نتائج سمات الشخصية لـ {user_info.get("name", "المستخدم")}',
        labels={'السمة': 'السمة', 'الدرجة': 'الدرجة'},
        color='السمة',
        color_discrete_map=trait_colors,
        template='plotly_dark'
    )
    fig.update_layout(
        title_x=0.5,
        font=dict(color='#FAFAFA'),
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# 3. Session State Initialization
# ==============================================================================
if 'page' not in st.session_state:
    st.session_state.page = 'onboarding'
if 'user_info' not in st.session_state:
    st.session_state.user_info = {}
if 'answered_traits' not in st.session_state:
    st.session_state.answered_traits = {}
if 'current_question_id' not in st.session_state:
    st.session_state.current_question_id = None
if 'current_question_text' not in st.session_state:
    st.session_state.current_question_text = ""
if 'current_question_trait' not in st.session_state:
    st.session_state.current_question_trait = ""
if 'asked_ids' not in st.session_state:
    st.session_state.asked_ids = set()
if 'question_count' not in st.session_state:
    st.session_state.question_count = 0
if 'test_started' not in st.session_state:
    st.session_state.test_started = False
if 'user_registered' not in st.session_state:
    st.session_state.user_registered = False
if 'last_score' not in st.session_state:
    st.session_state.last_score = None
if 'show_results_page' not in st.session_state:
    st.session_state.show_results_page = False
if 'registration_status' not in st.session_state:
    st.session_state.registration_status = ""
if 'results_saved_to_sheets' not in st.session_state:
    st.session_state.results_saved_to_sheets = False

# ==============================================================================
# 4. Load Questions Data
# ==============================================================================
QUESTIONS_DF = load_questions_data("edit.xlsx")

# ==============================================================================
# 5. Application Logic Processing Functions
# ==============================================================================
def register_user_callback(name, age, location):
    if not name or not age or not location:
        st.session_state.registration_status = "❌ يرجى ملء جميع الحقول."
        st.session_state.user_registered = False
        st.rerun()
        return
    if age < 13 or age > 120:
        st.session_state.registration_status = "❌ يرجى إدخال عمر صحيح (13-120)."
        st.session_state.user_registered = False
        st.rerun()
        return
    st.session_state.user_info = {
        "name": name,
        "age": age,
        "location": location,
        "test_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    st.session_state.user_registered = True
    st.session_state.registration_status = f"✅ تم تسجيل المستخدم: {name}"
    st.session_state.page = 'test'
    st.rerun()

def submit_answer_callback(answer_selected):
    if st.session_state.current_question_id is None or not st.session_state.test_started:
        st.warning("❌ لا يوجد سؤال حالي أو الاختبار لم يبدأ.")
        st.rerun()
        return
    if answer_selected not in CHOICES:
        st.warning("يرجى اختيار إجابة صحيحة.")
        st.rerun()
        return
    trait = st.session_state.current_question_trait
    score = CHOICE_VALUES[CHOICES.index(answer_selected)]
    if trait not in st.session_state.answered_traits:
        st.session_state.answered_traits[trait] = []
    st.session_state.answered_traits[trait].append(score)
    st.session_state.last_score = score
    st.session_state.question_count += 1
    if st.session_state.question_count >= MAX_QUESTIONS:
        st.session_state.test_started = False
        st.session_state.show_results_page = True
        st.session_state.page = 'results'
        st.rerun()
    else:
        question_text, error_message = get_next_question_logic(QUESTIONS_DF, st.session_state)
        if error_message:
            st.error(error_message)
        st.rerun()

def reset_test_callback():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.page = 'onboarding'
    st.rerun()

# ==============================================================================
# 6. Build Streamlit Interface
# ==============================================================================
st.set_page_config(
    page_title="اختبار الشخصية التكيفي (النموذج الخماسي)",
    layout="centered",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    body {
        background-color: #0E1117;
        color: #FAFAFA;
        direction: rtl;
        text-align: right;
        font-family: 'Arial', 'Helvetica', sans-serif;
    }
    .main .block-container {
        padding-top: 2rem;
        padding-right: 2rem;
        padding-left: 2rem;
        padding-bottom: 2rem;
        max-width: 700px;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #FAFAFA;
        font-weight: 600;
    }
    .st-emotion-cache-nahz7x {
        background-color: #1A1D21;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3), 0 2px 5px rgba(0, 128, 128, 0.2);
        padding: 25px;
        margin-bottom: 20px;
        animation: fadeIn 0.8s ease-out;
    }
    .stButton>button {
        background: linear-gradient(135deg, hsl(180 100% 25%), hsl(180 100% 35%));
        color: white;
        border-radius: 8px;
        border: none;
        padding: 12px 25px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 3px 10px rgba(0, 128, 128, 0.3);
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, hsl(180 100% 30%), hsl(180 100% 40%));
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0, 128, 128, 0.4);
    }
    .stTextInput input, .stNumberInput input {
        background-color: #2D323A;
        color: #FAFAFA;
        border: 1px solid #4A5057;
        border-radius: 8px;
        padding: 10px;
    }
    .stRadio div[role="radiogroup"] {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    .stRadio label {
        background-color: #2D323A;
        border: 1px solid #4A5057;
        border-radius: 8px;
        padding: 12px 15px;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 17px;
        color: #FAFAFA;
    }
    .stRadio label:hover {
        background-color: #3A4048;
        border-color: #00B3B3;
    }
    .stRadio input:checked + div {
        background-color: rgba(0, 128, 128, 0.4);
        border-color: #00B3B3;
    }
    .stProgress > div > div > div > div {
        background-color: #00B3B3; /* Default color, will be overridden by custom CSS */
    }
    .custom-progress {
        margin: 10px 0;
    }
    .custom-progress .stProgress > div > div > div > div {
        transition: width 0.5s ease-in-out;
    }
    .brain-icon-container {
        background: radial-gradient(circle, #00B3B3, #008080);
        border-radius: 50%;
        width: 80px;
        height: 80px;
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 0 auto 20px auto;
        box-shadow: 0 0 15px rgba(0, 128, 128, 0.6);
        font-size: 40px;
        color: white;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    /* Custom CSS for colored progress bars and labels */
    [data-testid="stProgress"] .stProgress > div > div > div > div {
        background-color: inherit; /* Reset to inherit for custom colors */
    }
    .progress-label {
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .trait-description {
        font-size: 1.0em;
        font-weight: bold;
        color: #FAFAFA;
        margin-top: 10px;
    }
    .trait-container {
        background-color: #1A1D21;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3), 0 2px 5px rgba(0, 128, 128, 0.2);
        padding: 15px;
        margin-bottom: 15px;
    }
    .sidebar-card {
        background-color: #1A1D21;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        box-shadow: 0 2px 5px rgba(0, 128, 128, 0.2);
    }
    .sidebar-card .icon {
        font-size: 24px;
        margin-bottom: 10px;
    }
    .sidebar-card .title {
        font-size: 1.2em;
        font-weight: bold;
        color: #FAFAFA;
        margin-bottom: 5px;
    }
    .sidebar-card .description {
        font-size: 0.9em;
        color: #B0B0B0;
    }
    .custom-title {
        background: linear-gradient(135deg, hsl(180 100% 25%), hsl(180 100% 35%));
        color: white;
        font-size: 1.5em;
        font-weight: 600;
        padding: 10px 15px;
        border-radius: 8px;
        box-shadow: 0 3px 10px rgba(0, 128, 128, 0.3);
        margin-bottom: 15px;
        text-align: center;
    }
    .dynamic-label {
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 10px;
        color: inherit; /* Will be dynamically set */
    }
    .question-box {
        background-color: #1A1D21;
        border: 2px solid #00B3B3;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        color: #FAFAFA;
        font-size: 1.2em;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar Navigation
st.sidebar.markdown('<div class="custom-title">التنقل</div>', unsafe_allow_html=True)
st.sidebar.markdown("""
<div class="sidebar-card">
    <div class="icon">⚙️</div>
    <div class="title">الاختبار التكيفي</div>
    <div class="description">نظامنا الذكي يقوم بتكييف الأسئلة بناءً على إجاباتك، مما يوفر تقييمًا أكثر دقة في عدد أقل من الأسئلة.</div>
</div>
<div class="sidebar-card">
    <div class="icon">👥</div>
    <div class="title">سمات الشخصية الخمس الكبرى</div>
    <div class="description">قم بقياس شخصيتك عبر خمسة أبعاد رئيسية: الانفتاح، الوعي، الانبساط، التوافق، والعصابية.</div>
</div>
<div class="sidebar-card">
    <div class="icon">📊</div>
    <div class="title">نتائج مفصلة</div>
    <div class="description">احصل على نتائج شاملة مع رسوم بيانية مرئية وتفسيرات مفصلة لملفك الشخصي.</div>
</div>
""", unsafe_allow_html=True)
if st.sidebar.button("بدء اختبار جديد", key="nav_start_test"):
    reset_test_callback()

# Page Logic
if st.session_state.page == 'onboarding':
    st.markdown("""
    <div class="brain-icon-container">
        🧠
    </div>
    <h1 style='text-align: center;'>مرحبًا بك في اختبار الشخصية التكيفي</h1>
    <p style='text-align: center; font-size: 1.1em;'>الرجاء إدخال بياناتك لبدء الاختبار القائم على النموذج الخماسي للشخصية.</p>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown("<h3 style='text-align: center;'>معلوماتك</h3>", unsafe_allow_html=True)
        with st.form("onboarding_form"):
            name = st.text_input("الاسم الكامل", key="name_input")
            age = st.number_input("السن", min_value=13, max_value=120, step=1, key="age_input")
            location = st.text_input("العنوان", key="location_input")
            submitted = st.form_submit_button("تسجيل المعلومات")
            if submitted:
                register_user_callback(name, age, location)
    if st.session_state.registration_status:
        if "✅" in st.session_state.registration_status:
            st.success(st.session_state.registration_status)
        else:
            st.error(st.session_state.registration_status)

elif st.session_state.page == 'test':
    st.markdown("<h1 style='text-align: center;'>اختبار الشخصية</h1>", unsafe_allow_html=True)
    if QUESTIONS_DF.empty:
        st.error("❌ لا توجد أسئلة متاحة في ملف 'edit.xlsx'. تأكد من وجود الملف وأنه يحتوي على الأعمدة الصحيحة.")
        st.stop()
    
    if not st.session_state.test_started:
        st.markdown("### يمكنك الآن بدء الاختبار!")
        if st.button("ابدأ الاختبار", key="start_test_button"):
            if not st.session_state.user_registered:
                st.session_state.registration_status = "❌ يرجى تسجيل معلوماتك أولاً."
                st.rerun()
            else:
                st.session_state.answered_traits = {}
                st.session_state.asked_ids = set()
                st.session_state.question_count = 0
                st.session_state.last_score = None
                st.session_state.test_started = True
                st.session_state.show_results_page = False
                question_text, error_message = get_next_question_logic(QUESTIONS_DF, st.session_state)
                if error_message:
                    st.error(error_message)
                    st.session_state.test_started = False
                else:
                    st.session_state.current_question_text = question_text
                st.rerun()
    else:
        progress_percentage = st.session_state.question_count / MAX_QUESTIONS
        st.progress(progress_percentage, text=f"التقدم: {st.session_state.question_count} / {MAX_QUESTIONS} سؤال")
        with st.container():
            st.markdown(f"<h2>السؤال {st.session_state.question_count + 1}</h2>", unsafe_allow_html=True)
            st.markdown(f'<div class="question-box">{st.session_state.current_question_text}</div>', unsafe_allow_html=True)
            with st.form("question_form"):
                color = TRAIT_COLORS.get(st.session_state.current_question_trait, '#00B3B3')
                st.markdown(f'<div class="dynamic-label" style="color: {color};">اختر إجابتك:</div>', unsafe_allow_html=True)
                answer = st.radio("", CHOICES, key=f"q_{st.session_state.question_count}", index=None, format_func=lambda x: x)
                if st.form_submit_button("السؤال التالي"):
                    submit_answer_callback(answer)

elif st.session_state.page == 'results':
    st.markdown("<h1 style='text-align: center;'>نتائج اختبار الشخصية</h1>", unsafe_allow_html=True)
    trait_scores, dominant_trait, dominant_score, summary_for_save = calculate_results(
        st.session_state.answered_traits, st.session_state.user_info
    )
    with st.container():
        st.markdown(f"<h3 style='color: #FAFAFA;'>مرحباً، {st.session_state.user_info.get('name', 'المستخدم')}!</h3>", unsafe_allow_html=True)
        st.write(f"السن: **{st.session_state.user_info.get('age', 'N/A')}** | العنوان: **{st.session_state.user_info.get('location', 'N/A')}**")
        st.markdown("<p style='font-size: 1.1em; color: #FAFAFA;'>إليك ملخص لسماتك الشخصية بناءً على إجاباتك:</p>", unsafe_allow_html=True)
    generate_report(trait_scores, TRAITS, TRAIT_COLORS, st.session_state.user_info)
    
    # Display progress bars for each trait with bordered containers and descriptions
    st.markdown("### درجات السمات الفردية")
    for trait in TRAITS:
        score = trait_scores.get(trait, 0.0)
        percentage = (score / 4) * 100  # Convert score (1-4) to percentage (0-100)
        color = TRAIT_COLORS[trait]
        description = TRAIT_DESCRIPTIONS[trait]
        with st.container():
            st.markdown(f'<div class="trait-container">', unsafe_allow_html=True)
            st.markdown(
                f'<div class="progress-label" style="color: {color};">{trait.replace(" (ذاتي)", "")}: {score:.2f}</div>',
                unsafe_allow_html=True
            )
            st.progress(percentage / 100)
            st.markdown(
                f'<div class="trait-description">{description}</div>',
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Display the dominant trait with its score
    st.markdown("### السمة الأساسية")
    st.write(f"بناءً على أعلى درجة، سمة الشخصية الأساسية لك هي: **{dominant_trait.replace(' (ذاتي)', '')}** بدرجة **{dominant_score:.2f}**.")

    if not st.session_state.results_saved_to_sheets:
        save_results_to_gsheets(st.session_state.user_info, trait_scores, dominant_trait)
        st.session_state.results_saved_to_sheets = True
    if st.button("إعادة تعيين الاختبار", key="reset_test_btn"):
        reset_test_callback()

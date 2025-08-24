import os
import streamlit as st
import requests
import pandas as pd
import altair as alt
import datetime
import matplotlib.pyplot as plt
import openai
import docx
import PyPDF2
import re

BACKEND_BASE = st.secrets.get("BACKEND_BASE_URL", "https://jobbuddy1-0.onrender.com")


# --- Email fetching function inlined ---
def fetch_job_emails():
    if "access_token" not in st.session_state or "refresh_token" not in st.session_state:
        return []
    headers = {
        'Access-Token': st.session_state["access_token"],
        'Refresh-Token': st.session_state["refresh_token"]
    }
    try:
        response = requests.get(f"{BACKEND_BASE}/emails", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Backend error: Status {response.status_code} - {response.text}")
            return []
    except Exception as e:
        st.error(f"Exception during fetch: {e}")
        return []



# --- Auth Utilities ---
def extract_tokens_from_url():
    # Try new API first
    try:
        qp = st.query_params
        access_token = qp.get("access_token", None)
        refresh_token = qp.get("refresh_token", None)
        # qp values might be lists depending on version
        if isinstance(access_token, list): access_token = access_token[0]
        if isinstance(refresh_token, list): refresh_token = refresh_token[0]
        if access_token and refresh_token:
            st.session_state["access_token"] = access_token
            st.session_state["refresh_token"] = refresh_token
            try:
                st.query_params.clear()
            except Exception:
                st.experimental_set_query_params()
            return True
    except Exception:
        pass

    # Fallback to experimental API
    try:
        qp = st.experimental_get_query_params()
        access_token = (qp.get("access_token", [None]) or [None])[0]
        refresh_token = (qp.get("refresh_token", [None]) or [None])[0]
        if access_token and refresh_token:
            st.session_state["access_token"] = access_token
            st.session_state["refresh_token"] = refresh_token
            st.experimental_set_query_params()
            return True
    except Exception:
        pass

    return False


def is_authenticated():
    return "access_token" in st.session_state and "refresh_token" in st.session_state


def logout():
    st.session_state.pop("access_token", None)
    st.session_state.pop("refresh_token", None)
    st.experimental_rerun()


def plot_interactive_calendar(df):
    # expects df['Date_Only'] as date
    df['Date_Only'] = pd.to_datetime(df['Date_Only'])
    # Aggregate applications per day
    heatmap_df = df.groupby('Date_Only').size().reset_index(name='Applications')
    heatmap_df['Day_Num'] = heatmap_df['Date_Only'].dt.weekday
    heatmap_df['Month_Num'] = heatmap_df['Date_Only'].dt.month
    heatmap_df['Month'] = heatmap_df['Date_Only'].dt.strftime('%b')
    heatmap_df['Day_Label'] = heatmap_df['Date_Only'].dt.day_name()

    base = alt.Chart(heatmap_df).encode(
        x=alt.X('Day_Num:O', title='Day of Week',
                axis=alt.Axis(labelExpr="{'0':'Mon','1':'Tue','2':'Wed','3':'Thu','4':'Fri','5':'Sat','6':'Sun'}[datum.label]")),
        y=alt.Y('Month:O', title='Month',
                sort=alt.EncodingSortField(field='Month_Num', order='ascending'))
    )

    heatmap = base.mark_rect().encode(
        color=alt.Color('Applications:Q', scale=alt.Scale(scheme='greens')),
        tooltip=[alt.Tooltip('Date_Only:T', title='Date'), alt.Tooltip('Applications:Q')]
    )

    borders = base.mark_rect(
        fillOpacity=0,
        stroke='black',
        strokeWidth=0.5
    )

    chart = (heatmap + borders).properties(
        width=700,
        height=400,
    )

    st.altair_chart(chart, use_container_width=True)


# --- Page renderers (home, dashboard, more analysis remain unchanged) ---
def render_home():
    st.title("💼 Welcome to Job Buddy1.0 : Your Companion for Job Search")

    st.write("This app helps you track and analyze your job applications automatically.")

    quotes = [
        "Believe you can and you're halfway there. – Theodore Roosevelt",
        "Your limitation—it’s only your imagination.",
        "Push yourself, because no one else is going to do it for you.",
        "Great things never come from comfort zones.",
        "Dream it. Wish it. Do it.",
        "Success doesn’t just find you. You have to go out and get it.",
        "The harder you work for something, the greater you’ll feel when you achieve it.",
        "Don’t watch the clock; do what it does. Keep going. – Sam Levenson",
        "Stay positive, work hard, make it happen.",
        "The future depends on what you do today. – Mahatma Gandhi"
    ]

    today = datetime.date.today()
    quote_of_the_day = quotes[today.toordinal() % len(quotes)]

    st.markdown(f"""
    <div style="background-color:#DFF6FF; padding:20px; border-radius:10px; margin-bottom:20px;">
        <h3 style="color:#007ACC; text-align:center;">✨ Daily Motivational Quote ✨</h3>
        <p style="font-style:italic; font-size:18px; text-align:center;">"{quote_of_the_day}"</p>
    </div>
    """, unsafe_allow_html=True)


def render_dashboard():
    st.title("🪞 Job Application: Reflexion")

    try:
        data = fetch_job_emails()
        df = pd.DataFrame(data)

        if not df.empty:
            st.success(f"✅ Found {len(df)} emails.")

            df['Date'] = pd.to_datetime(df['Date'], errors='coerce', utc=True).dt.tz_convert(None)
            df = df.dropna(subset=['Date'])

            df['Year'] = df['Date'].dt.year
            df['Week_Num'] = df['Date'].dt.isocalendar().week
            df['Date_Only'] = df['Date'].dt.date

            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            last_7_days = today - datetime.timedelta(days=7)

            jobs_today = df[df['Date_Only'] == today]
            jobs_yesterday = df[df['Date_Only'] == yesterday]
            jobs_last_7_days = df[df['Date_Only'] >= last_7_days]

            col1, col2, col3 = st.columns(3)
            col1.metric("🟢 Jobs Applied Today", len(jobs_today))
            col2.metric("🕒 Jobs Applied Yesterday", len(jobs_yesterday))
            col3.metric("📆 Jobs Applied Last 7 Days", len(jobs_last_7_days))

            # ➕ Calculate average jobs per day
            daily_counts = df.groupby('Date_Only').size()
            average_per_day = round(daily_counts.mean())  # Rounded to nearest integer
            st.metric("📊 Avg Jobs/Day", f"{average_per_day}")

            # 🧠 Smart motivational message
            jobs_today_count = len(jobs_today)
            if jobs_today_count > average_per_day:
                st.success(f"👏 You're on fire! You've applied to {jobs_today_count} jobs today, which is **more than your daily average** of {average_per_day}. Keep it up! 🚀😄")
            elif jobs_today_count < average_per_day:
                st.info(f"🙌 You’ve applied to {jobs_today_count} jobs today, which is **less than your average** of {average_per_day}. Keep going — small steps matter! 🌱💪")
            else:
                st.warning(f"🔁 You’re right on track! Today’s applications match your average of {average_per_day}. Consistency is key! 🎯")

            st.markdown("---")

            # Date filters and daily line chart
            start_of_this_month = today.replace(day=1)
            start_of_last_month = (start_of_this_month - datetime.timedelta(days=1)).replace(day=1)
            end_of_last_month = start_of_this_month - datetime.timedelta(days=1)
            two_weeks_ago = today - datetime.timedelta(days=14)

            st.markdown("### 📅 Filter Daily Trend by Time Range")
            date_filter = st.selectbox(
                "Select Time Range",
                ["Last 2 Weeks", "This Month", "Last Month", "All Time"]
            )

            if date_filter == "Last 2 Weeks":
                df_filtered = df[df['Date_Only'] >= two_weeks_ago]
            elif date_filter == "This Month":
                df_filtered = df[df['Date_Only'] >= start_of_this_month]
            elif date_filter == "Last Month":
                df_filtered = df[(df['Date_Only'] >= start_of_last_month) & (df['Date_Only'] <= end_of_last_month)]
            else:
                df_filtered = df

            daily_trend = df_filtered.groupby('Date_Only').size().reset_index(name='Applications')
            daily_trend = daily_trend.sort_values('Date_Only')

            chart = alt.Chart(daily_trend).mark_line(point=True).encode(
                x=alt.X('Date_Only:T', title='Date', axis=alt.Axis(labelAngle=0)),
                y=alt.Y('Applications', title='Jobs Applied'),
                tooltip=['Date_Only:T', 'Applications']
            ).properties(
                title=f"📈 Daily Job Application Trend ({date_filter})",
                width=700,
                height=300
            )

            st.altair_chart(chart, use_container_width=True)

            csv = df.to_csv(index=False)
            st.download_button("📥 Download Job Data as CSV", csv, "job_applications.csv", "text/csv")

            with st.expander("🔍 Raw Email Data"):
                st.dataframe(df[['Date', 'Subject', 'From']].sort_values(by='Date', ascending=False))
        else:
            st.warning("No job-related emails found.")
    except Exception as e:
        st.error(f"Error: {e}")


def render_more_analysis():
    try:
        data = fetch_job_emails()
        df = pd.DataFrame(data)

        if not df.empty:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce', utc=True).dt.tz_convert(None)
            df = df.dropna(subset=['Date'])
            df['Date_Only'] = df['Date'].dt.date
            today = datetime.date.today()

            # --- WEEKLY ANALYSIS SECTION ---
            st.markdown("## 📆 Weekly Job Application Goal & Progress")

            # Weekly Goal Tracker - editable in sidebar
            weekly_goal = st.sidebar.number_input(
                "Set your weekly job application goal:",
                min_value=1,
                max_value=100,
                value=10,
                step=1,
                help="Set your target number of job applications per week"
            )

            # Calculate weekly application progress
            df['Year_Week'] = df['Date'].dt.strftime('%G-W%V')  # ISO year-week
            current_week = today.isocalendar()
            current_year_week = f"{current_week[0]}-W{str(current_week[1]).zfill(2)}"
            weekly_apps = df[df['Year_Week'] == current_year_week]
            count_weekly_apps = len(weekly_apps)

            progress_percent = int((count_weekly_apps / weekly_goal) * 100) if weekly_goal > 0 else 0
            progress_percent = min(progress_percent, 100)  # Cap at 100%
            progress_text = f"📅 This Week: {count_weekly_apps} / {weekly_goal} applications"

            st.markdown("### 🏁 Weekly Application Goal Tracker")
            st.progress(progress_percent)
            st.info(progress_text)

            # Optional: Last 5 weeks summary
            weekly_summary = df.groupby('Year_Week').size().reset_index(name='Applications')
            weekly_summary = weekly_summary.sort_values('Year_Week', ascending=False).head(5)

            with st.expander("📊 Weekly History (Last 5 Weeks)"):
                st.dataframe(weekly_summary, use_container_width=True)

            # --- MONTHLY/CONSISTENCY ANALYSIS SECTION ---
            st.markdown("## 📅 Monthly Analysis & Application Consistency")
            st.markdown("Check out the heatmap below to see how consistent you’ve been over time. It visualizes your job applications across different days and months.")

            st.markdown("### 🗓️ Calendar Heatmap of Applications")
            plot_interactive_calendar(df)

        else:
            st.warning("No job-related emails found.")
    except Exception as e:
        st.error(f"Error: {e}")


def render_tracking():
    st.title("📊 Job Application & Status")
    st.info("🚧 This feature is coming soon! You'll be able to track your applications and their statuses here.")


def render_resume_analyzer():
    st.title("🕵️‍♂️ Resume vs Job Description Analyzer (Zero Cost)")

    st.write("Upload your resume and job description (PDF or DOCX). This tool analyzes keyword match without any API or subscription.")

    def extract_text_from_pdf(uploaded_file):
        try:
            reader = PyPDF2.PdfReader(uploaded_file)
            text_pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(text_pages)
        except Exception:
            return ""

    def extract_text_from_docx(uploaded_file):
        try:
            doc = docx.Document(uploaded_file)
            return "\n".join([para.text for para in doc.paragraphs if para.text])
        except Exception:
            return ""

    def simple_keyword_match_analysis(resume_text, jd_text):
        stopwords = set(["and", "or", "the", "a", "an", "with", "to", "for", "of", "in", "on", "is", "are", "you", "your"])
        jd_words = re.findall(r'\b\w+\b', jd_text.lower())
        jd_keywords = set([w for w in jd_words if w not in stopwords and len(w) > 2])

        resume_words = set(re.findall(r'\b\w+\b', resume_text.lower()))

        matched = jd_keywords.intersection(resume_words)
        missing = jd_keywords - resume_words

        if len(jd_keywords) == 0:
            match_percent = 0
        else:
            match_percent = int(len(matched) / len(jd_keywords) * 100)

        feedback = f"Match: {match_percent}%\n\n"

        if match_percent >= 75:
            feedback += "✅ Strong match! You should apply.\n"
        else:
            feedback += "⚠️ Needs improvement before applying.\n\n"
            feedback += "Missing or weak skills:\n"
            for skill in list(missing)[:5]:
                feedback += f"- {skill}\n"
            feedback += "\nStep-by-step plan to improve:\n"
            feedback += "1. Add missing skills as bullet points in your resume.\n"
            feedback += "2. Use keywords exactly as they appear in the job description.\n"
            feedback += "3. Rewrite existing bullet points to emphasize relevant skills.\n"
            feedback += "\nExample bullet points to add:\n"
            for skill in list(missing)[:3]:
                feedback += f"- Developed expertise in {skill} to achieve project goals.\n"
            feedback += "\nFocus on these improvements before applying.\n"

        return feedback

    resume_file = st.file_uploader("📄 Upload your Resume (PDF or DOCX)", type=["pdf", "docx"])
    jd_file = st.file_uploader("📃 Upload the Job Description (PDF or DOCX)", type=["pdf", "docx"])

    if resume_file and jd_file:
        if resume_file.name.lower().endswith(".pdf"):
            resume_text = extract_text_from_pdf(resume_file)
        else:
            resume_text = extract_text_from_docx(resume_file)

        if jd_file.name.lower().endswith(".pdf"):
            jd_text = extract_text_from_pdf(jd_file)
        else:
            jd_text = extract_text_from_docx(jd_file)

        if not resume_text or not jd_text:
            st.warning("⚠️ Could not extract text from one or both files. Please check the formats.")
            return

        if st.button("🔍 Analyze"):
            with st.spinner("Analyzing..."):
                feedback = simple_keyword_match_analysis(resume_text, jd_text)

            st.success("✅ Analysis complete!")

            st.markdown("### 📋 Feedback")
            st.text_area("", value=feedback, height=400)

            # Extract match % and show progress bar
            match = re.search(r"Match:\s*(\d{1,3})\s*%", feedback)
            if match:
                match_score = int(match.group(1))
                st.subheader(f"📊 Match Score: {match_score}%")
                st.progress(match_score / 100)
                if match_score >= 75:
                    st.success("✅ Strong match! You should apply!")
                else:
                    st.warning("⚠️ Needs improvement before applying.")
    else:
        st.info("👆 Please upload both Resume and Job Description to begin.")




# --- Main ---
def main():
    st.set_page_config(page_title="Job Tracker", page_icon="💼", layout="wide")

    extract_tokens_from_url()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["🏠 Home", "📊 Dashboard", "📈 More Analysis", "📆Trackig", "🕵️‍♂️Resume Analyzer"])

    if not is_authenticated():
        st.info("🔐 Please login first to fetch your job emails.")
        if st.button("Login with Gmail"):
           try:
            # Streamlit 1.25+ has a handy link button; fall back to markdown if not present
            st.link_button("Click here to login", f"{BACKEND_BASE}/login")
           except Exception:
            st.markdown(f"[Click here to login]({BACKEND_BASE}/login)", unsafe_allow_html=True)


    st.success("✅ You are authenticated!")

    if st.button("Logout"):
        logout()

    if page == "🏠 Home":
        render_home()
    elif page == "📊 Dashboard":
        render_dashboard()
    elif page == "📈 More Analysis":
        render_more_analysis()
    elif page == "📆Trackig":
        render_tracking()
    elif page == "🕵️‍♂️Resume Analyzer":
        render_resume_analyzer()


if __name__ == "__main__":
    main()

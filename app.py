import os
import re
import json
from datetime import datetime, timezone

import requests
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Face Safety App", page_icon="🛡️", layout="wide")

st.title("🛡️ Face Safety App")
st.caption("Consent-based personal safety monitoring prototype")

# ---------- Configuration ----------
def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_ANON_KEY")
NEWS_API_KEY = get_secret("NEWS_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase configuration missing.")
    st.info("Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml and add your credentials.")
    st.stop()

@st.cache_resource
def get_supabase_client(url, key):
    return create_client(url, key)

try:
    sb = get_supabase_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as exc:
    st.error(f"Could not initialize Supabase: {exc}")
    st.stop()

# ---------- Helpers ----------
def current_user():
    return st.session_state.get("user")

def save_consent(user_id, kind, granted):
    sb.table("consents").insert({
        "user_id": user_id,
        "kind": kind,
        "granted": bool(granted),
        "policy_version": "2026-10-v1"
    }).execute()

def latest_consent(user_id, kind):
    try:
        result = (sb.table("consents").select("granted")
                  .eq("user_id", user_id).eq("kind", kind)
                  .order("created_at", desc=True).limit(1).execute())
        return bool(result.data and result.data[0]["granted"])
    except Exception:
        return False

def get_profile(user_id):
    result = sb.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    return result.data[0] if result.data else {}

def save_finding(user_id, category, source_url, title, excerpt, label, score):
    sb.table("findings").insert({
        "user_id": user_id,
        "category": category,
        "source_url": source_url or None,
        "title": title or "Manual review",
        "excerpt": (excerpt or "")[:2000],
        "ai_label": label,
        "ai_score": float(score),
        "status": "needs_review"
    }).execute()

def safe_float(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0

# ---------- Optional toxicity model ----------
@st.cache_resource(show_spinner="Loading optional text-analysis model...")
def load_toxicity_model():
    try:
        from transformers import pipeline
        return pipeline(
            "text-classification",
            model="unitary/toxic-bert",
            top_k=None
        )
    except Exception:
        return None

TOXIC_LABELS = {
    "toxic", "severe_toxicity", "threat",
    "insult", "identity_hate", "obscene"
}

def analyze_text(text):
    text = (text or "").strip()[:2000]
    if not text:
        return 0.0, "empty"

    model = load_toxicity_model()
    if model:
        try:
            output = model(text[:512])
            if output and isinstance(output[0], list):
                output = output[0]
            scores = [
                safe_float(item.get("score"))
                for item in output
                if item.get("label", "").lower() in TOXIC_LABELS
            ]
            if scores:
                score = max(scores)
                return score, "model_review" if score >= 0.5 else "low_model_score"
        except Exception:
            pass

    # Transparent fallback: keyword flag only, not a classifier.
    terms = [
        "kill you", "i will hurt you", "threat", "blackmail",
        "ধর্ষণ", "মেরে ফেলব", "হুমকি", "ব্ল্যাকমেইল"
    ]
    lowered = text.lower()
    if any(term in lowered for term in terms):
        return 0.75, "keyword_flag"
    return 0.0, "no_keyword_flag"

# ---------- News search ----------
def search_news(query):
    if not NEWS_API_KEY:
        raise RuntimeError("NEWS_API_KEY is not configured.")
    response = requests.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": NEWS_API_KEY
        },
        timeout=20
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise RuntimeError(payload.get("message", "News API request failed"))
    return payload.get("articles", [])

def article_matches(article, full_name, usernames):
    text = f"{article.get('title') or ''} {article.get('description') or ''}".lower()
    name = (full_name or "").strip().lower()
    if name and name in text:
        return True
    for username in usernames:
        candidate = username.strip().lower().lstrip("@")
        if candidate and re.search(rf"(?<!\w)@?{re.escape(candidate)}(?!\w)", text):
            return True
    return False

# ---------- Authentication ----------
def auth_screen():
    st.subheader("Account")
    tab_login, tab_signup = st.tabs(["Login", "Sign up"])

    with tab_login:
        email = st.text_input("Email address", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", use_container_width=True):
            try:
                result = sb.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = result.user
                st.success("Login successful.")
                st.rerun()
            except Exception as exc:
                st.error(f"Login failed: {exc}")

    with tab_signup:
        new_email = st.text_input("Email address", key="signup_email")
        new_password = st.text_input("Password (minimum 8 characters)", type="password", key="signup_password")
        if st.button("Create account", use_container_width=True):
            if len(new_password) < 8:
                st.warning("Please use at least 8 characters.")
            else:
                try:
                    result = sb.auth.sign_up({"email": new_email, "password": new_password})
                    if result.user:
                        st.success("Account created. Check your email if confirmation is enabled, then log in.")
                except Exception as exc:
                    st.error(f"Sign-up failed: {exc}")

user = current_user()
if not user:
    auth_screen()
    st.stop()

user_id = user.id
st.sidebar.success(f"Signed in: {user.email or user_id}")
if st.sidebar.button("Log out"):
    try:
        sb.auth.sign_out()
    finally:
        st.session_state.clear()
        st.rerun()

# ---------- Main application ----------
profile_tab, news_tab, text_tab, findings_tab, privacy_tab = st.tabs(
    ["Profile & Consent", "News Review", "Text Review", "Findings", "Privacy"]
)

with profile_tab:
    st.subheader("Your profile")
    try:
        profile = get_profile(user_id)
    except Exception as exc:
        profile = {}
        st.error(f"Could not load profile: {exc}")

    full_name = st.text_input("Full name", value=profile.get("full_name", ""))
    usernames_text = st.text_input(
        "Public usernames (comma-separated)",
        value=", ".join(profile.get("usernames") or [])
    )
    context = st.text_area("Optional context for human reviewers", value=profile.get("context") or "")

    st.markdown("#### Consent settings")
    own_default = latest_consent(user_id, "own_photos")
    photo_default = latest_consent(user_id, "face_processing")
    news_default = latest_consent(user_id, "news_monitoring")

    own = st.checkbox("I confirm that the uploaded photo is mine or I have authority to provide it.", value=own_default)
    photo_consent = st.checkbox("I consent to storing and processing my own uploaded selfie.", value=photo_default)
    news_consent = st.checkbox("I consent to searching public news for my name/usernames.", value=news_default)

    selfie = st.file_uploader("Optional selfie (JPG or PNG)", type=["jpg", "jpeg", "png"])
    st.caption("This prototype stores the selfie only when you confirm ownership and photo-processing consent.")

    if st.button("Save profile and consent", type="primary"):
        try:
            existing_path = profile.get("selfie_path")
            selfie_path = existing_path

            if selfie and not (own and photo_consent):
                st.error("Confirm ownership and photo-processing consent before uploading.")
            else:
                if selfie:
                    ext = "png" if selfie.type == "image/png" else "jpg"
                    selfie_path = f"{user_id}/selfie.{ext}"
                    sb.storage.from_("selfies").upload(
                        selfie_path, selfie.getvalue(),
                        {"content-type": selfie.type, "upsert": "true"}
                    )
                elif not photo_consent and existing_path:
                    try:
                        sb.storage.from_("selfies").remove([existing_path])
                    except Exception as storage_exc:
                        st.warning(f"Could not remove old selfie automatically: {storage_exc}")
                    selfie_path = None

                sb.table("profiles").upsert({
                    "id": user_id,
                    "full_name": full_name.strip(),
                    "usernames": [x.strip().lstrip("@") for x in usernames_text.split(",") if x.strip()],
                    "context": context.strip() or None,
                    "selfie_path": selfie_path,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).execute()

                # Always record both grants and withdrawals.
                save_consent(user_id, "own_photos", own)
                save_consent(user_id, "face_processing", photo_consent)
                save_consent(user_id, "news_monitoring", news_consent)
                st.success("Profile and consent preferences saved.")
                st.rerun()
        except Exception as exc:
            st.error(f"Profile save failed: {exc}")

with news_tab:
    st.subheader("Public news review")
    st.warning("News search results are possible matches only. They do not verify identity or prove wrongdoing.")
    try:
        profile = get_profile(user_id)
    except Exception:
        profile = {}

    if not latest_consent(user_id, "news_monitoring"):
        st.info("News monitoring consent is not active. Enable it in Profile & Consent first.")
    elif not profile.get("full_name"):
        st.info("Please save your full name in Profile & Consent first.")
    else:
        if st.button("Search public news", type="primary"):
            try:
                queries = [profile["full_name"]]
                queries.extend(profile.get("usernames") or [])
                collected = []
                seen = set()
                for query in queries[:5]:
                    for article in search_news(query):
                        url = article.get("url") or ""
                        if url and url not in seen and article_matches(article, profile["full_name"], profile.get("usernames") or []):
                            seen.add(url)
                            collected.append(article)
                st.session_state.news_results = collected
            except Exception as exc:
                st.error(f"News search failed: {exc}")

        for i, article in enumerate(st.session_state.get("news_results", [])):
            with st.container(border=True):
                st.write(article.get("title") or "Untitled")
                st.caption(article.get("source", {}).get("name", "Unknown source"))
                st.write(article.get("description") or "")
                if article.get("url"):
                    st.markdown(f"[Open original article]({article['url']})")
                if st.button("Save for human review", key=f"save_news_{i}"):
                    try:
                        save_finding(user_id, "news", article.get("url"), article.get("title"),
                                     article.get("description"), "unverified_match", 0.0)
                        st.success("Saved for review.")
                    except Exception as exc:
                        st.error(f"Could not save: {exc}")

with text_tab:
    st.subheader("Text safety review")
    st.caption("Use text you are authorized to review. The score is an automated signal, not a factual conclusion.")
    text_input = st.text_area("Paste text for review", height=180)
    source_url = st.text_input("Source URL (optional)")
    if st.button("Analyze text"):
        score, label = analyze_text(text_input)
        st.session_state.text_result = {
            "score": score, "label": label,
            "text": text_input, "url": source_url
        }
    result = st.session_state.get("text_result")
    if result:
        st.metric("Review score", f"{result['score']:.0%}")
        st.write(f"Signal: `{result['label']}`")
        if st.button("Save text for human review"):
            try:
                save_finding(user_id, "text", result["url"], "User-submitted text",
                             result["text"], result["label"], result["score"])
                st.success("Saved for review.")
                st.session_state.pop("text_result", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save finding: {exc}")

with findings_tab:
    st.subheader("Saved findings")
    try:
        result = (sb.table("findings").select("*").eq("user_id", user_id)
                  .order("created_at", desc=True).limit(100).execute())
        if not result.data:
            st.info("No saved findings yet.")
        for row in result.data:
            with st.container(border=True):
                st.write(row.get("title") or row.get("category"))
                st.caption(f"{row.get('category')} · {row.get('status')} · score {safe_float(row.get('ai_score')):.0%}")
                st.write(row.get("excerpt") or "")
                if row.get("source_url"):
                    st.markdown(f"[Open source]({row['source_url']})")
                status = st.selectbox(
                    "Human review status",
                    ["needs_review", "confirmed_by_user", "rejected_by_user"],
                    index=["needs_review", "confirmed_by_user", "rejected_by_user"].index(row.get("status", "needs_review"))
                    if row.get("status") in ["needs_review", "confirmed_by_user", "rejected_by_user"] else 0,
                    key=f"status_{row['id']}"
                )
                if st.button("Update status", key=f"update_{row['id']}"):
                    sb.table("findings").update({"status": status}).eq("id", row["id"]).eq("user_id", user_id).execute()
                    st.success("Status updated.")
                    st.rerun()
    except Exception as exc:
        st.error(f"Could not load findings: {exc}")

with privacy_tab:
    st.subheader("Privacy and account data")
    st.write("You can withdraw monitoring consent in Profile & Consent. Deleting your account data is a separate action.")
    if st.button("Withdraw all monitoring/photo consents"):
        try:
            for kind in ["own_photos", "face_processing", "news_monitoring"]:
                save_consent(user_id, kind, False)
            st.success("Consent withdrawal recorded. Save profile to complete any pending selfie cleanup.")
        except Exception as exc:
            st.error(f"Could not record withdrawal: {exc}")

    st.divider()
    st.error("Permanent deletion cannot be undone.")
    confirm_delete = st.checkbox("I understand that this will permanently delete my profile and findings.")
    if st.button("Delete my application data", disabled=not confirm_delete):
        try:
            profile = get_profile(user_id)
            if profile.get("selfie_path"):
                try:
                    sb.storage.from_("selfies").remove([profile["selfie_path"]])
                except Exception as storage_exc:
                    st.warning(f"Selfie cleanup needs manual verification: {storage_exc}")
            sb.table("findings").delete().eq("user_id", user_id).execute()
            sb.table("profiles").delete().eq("id", user_id).execute()
            for kind in ["own_photos", "face_processing", "news_monitoring"]:
                save_consent(user_id, kind, False)
            st.success("Application profile and findings deleted. Sign out from your Supabase account separately if required.")
            st.rerun()
        except Exception as exc:
            st.error(f"Deletion failed: {exc}")

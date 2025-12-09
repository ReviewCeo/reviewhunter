import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import os
import time

# Konfiguration
st.set_page_config(
    page_title="ReviewHunter",
    page_icon="🎯",
    layout="wide"
)

# API Keys aus Secrets
OUTSCRAPER_API_KEY = st.secrets.get("OUTSCRAPER_API_KEY", os.getenv("OUTSCRAPER_API_KEY", ""))

# Branchen-Multiplikatoren
BRANCH_FACTORS = {
    "Zahnarzt": 1.3,
    "Arzt": 1.3,
    "Anwalt": 1.25,
    "Steuerberater": 1.25,
    "Restaurant": 1.1,
    "Hotel": 1.1,
    "Café": 1.1,
    "Fitness": 1.0,
    "Physiotherapie": 1.0,
    "Friseur": 1.0,
    "Kosmetik": 1.0,
    "Handwerker": 0.9,
    "Autohaus": 0.95,
    "Imbiss": 0.8,
    "Kiosk": 0.8
}

# Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #D4A445;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #888;
        margin-top: 0;
    }
    .score-hot { 
        background-color: #22C55E33; 
        color: #22C55E; 
        font-weight: bold;
        padding: 2px 8px;
        border-radius: 4px;
    }
    .score-warm { 
        background-color: #F59E0B33; 
        color: #F59E0B; 
        font-weight: bold;
        padding: 2px 8px;
        border-radius: 4px;
    }
    .score-cold { 
        background-color: #3B82F633; 
        color: #3B82F6; 
        font-weight: bold;
        padding: 2px 8px;
        border-radius: 4px;
    }
    .score-none { 
        background-color: #6B728033; 
        color: #6B7280; 
        padding: 2px 8px;
        border-radius: 4px;
    }
    .api-info {
        background: #1a1a1a;
        padding: 10px;
        border-radius: 8px;
        border-left: 4px solid #D4A445;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


def search_businesses_outscraper(query: str, location: str, api_key: str, limit: int = 20) -> list:
    """
    Sucht Businesses via Outscraper Google Maps API
    Liefert mehr Ergebnisse als Google Places API
    """
    
    url = "https://api.app.outscraper.com/maps/search-v3"
    
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    
    params = {
        "query": f"{query} in {location}",
        "limit": limit,
        "language": "de",
        "region": "DE",
        "async": False
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        # Outscraper gibt Liste von Listen zurück
        if result and len(result) > 0:
            return result[0] if isinstance(result[0], list) else result
        return []
    except requests.exceptions.Timeout:
        st.error("⏱️ Timeout - Anfrage dauerte zu lange. Versuche weniger Ergebnisse.")
        return []
    except Exception as e:
        st.error(f"API Fehler: {str(e)}")
        return []


def get_reviews_outscraper(place_id: str, api_key: str, reviews_limit: int = 20) -> list:
    """
    Holt Reviews für ein Business via Outscraper
    Inkludiert owner_response Feld!
    """
    
    url = "https://api.app.outscraper.com/maps/reviews-v3"
    
    headers = {
        "X-API-KEY": api_key
    }
    
    params = {
        "query": place_id,
        "reviewsLimit": reviews_limit,
        "language": "de",
        "sort": "newest",
        "async": False
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result and len(result) > 0:
            place_data = result[0]
            return place_data.get("reviews_data", [])
        return []
    except:
        return []


def analyze_reviews_outscraper(reviews: list) -> dict:
    """
    Analysiert Reviews auf Owner Responses
    Outscraper liefert owner_response Feld direkt!
    """
    
    if not reviews:
        return {
            "total": 0,
            "answered": 0,
            "unanswered": 0,
            "unanswered_pct": 100,
            "last_negative_days": 999
        }
    
    total = len(reviews)
    answered = 0
    last_negative_days = 999
    
    now = datetime.now()
    
    for review in reviews:
        # Outscraper liefert owner_response direkt
        owner_response = review.get("owner_response") or review.get("response_text")
        if owner_response:
            answered += 1
        
        # Rating checken (1-3 = negativ)
        rating = review.get("review_rating", 5)
        if rating and rating <= 3:
            review_date_str = review.get("review_datetime_utc") or review.get("review_date")
            if review_date_str:
                try:
                    if isinstance(review_date_str, str):
                        review_date = datetime.fromisoformat(review_date_str.replace("Z", "+00:00"))
                        days_ago = (now - review_date.replace(tzinfo=None)).days
                        if days_ago < last_negative_days:
                            last_negative_days = days_ago
                except:
                    pass
    
    unanswered = total - answered
    unanswered_pct = (unanswered / total * 100) if total > 0 else 0
    
    return {
        "total": total,
        "answered": answered,
        "unanswered": unanswered,
        "unanswered_pct": unanswered_pct,
        "last_negative_days": last_negative_days
    }


def calculate_lead_score(rating: float, review_count: int, unanswered_pct: float, 
                         last_negative_days: int, branche: str) -> tuple:
    """
    Berechnet Lead-Score v2.1 (0-100+)
    """
    
    # Faktor 1: Antwortverhalten (max 35 Punkte)
    f1 = 0
    if unanswered_pct == 0:
        f1 = 0
    elif unanswered_pct <= 25:
        f1 = 10
    elif unanswered_pct <= 50:
        f1 = 20
    elif unanswered_pct <= 75:
        f1 = 28
    else:
        f1 = 35
    
    # Faktor 2: Rating-Problem (max 25 Punkte)
    f2 = 0
    if rating:
        if rating < 3.0:
            f2 = 25
        elif rating < 3.5:
            f2 = 20
        elif rating < 4.0:
            f2 = 15
        elif rating < 4.5:
            f2 = 8
        else:
            f2 = 0
    else:
        f2 = 12
    
    if review_count < 10:
        f2 = int(f2 * 0.5)
    
    # Faktor 3: Volumen (max 20 Punkte)
    f3 = 0
    if review_count >= 100:
        f3 = 20
    elif review_count >= 31:
        f3 = 15
    elif review_count >= 10:
        f3 = 10
    elif review_count >= 5:
        f3 = 5
    else:
        f3 = 0
    
    # Faktor 4: Aktualität (max 10 Punkte)
    f4 = 0
    if last_negative_days <= 7:
        f4 = 10
    elif last_negative_days <= 30:
        f4 = 7
    elif last_negative_days <= 90:
        f4 = 4
    else:
        f4 = 0
    
    raw_score = f1 + f2 + f3 + f4
    branch_factor = BRANCH_FACTORS.get(branche, 1.0)
    final_score = round(raw_score * branch_factor)
    
    breakdown = {
        "antwort": f1,
        "rating": f2,
        "volumen": f3,
        "aktualitaet": f4,
        "raw": raw_score,
        "factor": branch_factor,
        "final": final_score
    }
    
    return final_score, breakdown


def get_pain_flags(rating: float, unanswered_pct: float, branch_factor: float, review_count: int) -> list:
    """Berechnet Pain-Flags für ein Business"""
    
    flags = []
    
    if rating and rating < 4.0:
        flags.append("🚨")
    
    if unanswered_pct > 50:
        flags.append("⏰")
    
    if branch_factor >= 1.2:
        flags.append("💰")
    
    if review_count >= 50:
        flags.append("📊")
    
    return flags


def get_score_category(score: int) -> tuple:
    if score >= 70:
        return "🔥 Hot", "score-hot"
    elif score >= 50:
        return "🟡 Warm", "score-warm"
    elif score >= 30:
        return "🔵 Cold", "score-cold"
    else:
        return "⚪ Low", "score-none"


# ============== MAIN APP ==============

st.markdown('<p class="main-header">🎯 ReviewHunter</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Finde Businesses mit schlechtem Review-Management</p>', unsafe_allow_html=True)

st.divider()

# Sidebar
with st.sidebar:
    st.header("⚙️ Einstellungen")
    
    if not OUTSCRAPER_API_KEY:
        api_key_input = st.text_input("Outscraper API Key", type="password")
        if api_key_input:
            OUTSCRAPER_API_KEY = api_key_input
    else:
        st.success("✅ API Key geladen")
    
    st.divider()
    
    result_limit = st.slider("Max. Businesses", 10, 100, 20, 10)
    reviews_per_business = st.slider("Reviews pro Business", 10, 50, 20, 5)
    
    st.divider()
    
    st.header("📊 Lead-Score")
    st.markdown("""
    **70+:** 🔥 Hot Lead  
    **50-69:** 🟡 Warm Lead  
    **30-49:** 🔵 Cold Lead  
    **0-29:** ⚪ Kein Lead
    """)
    
    st.divider()
    
    st.header("🏷️ Pain-Flags")
    st.markdown("""
    🚨 Rating < 4.0  
    ⏰ >50% unbeantwortet  
    💰 High-Value Branche  
    📊 50+ Reviews
    """)

# Hauptbereich
col1, col2 = st.columns([1, 1])

with col1:
    branche = st.selectbox(
        "Branche",
        ["Friseur", "Restaurant", "Zahnarzt", "Kosmetik", "Fitness", "Physiotherapie", 
         "Handwerker", "Autohaus", "Hotel", "Café", "Arzt", "Anwalt", "Steuerberater"]
    )

with col2:
    location = st.text_input("Stadt / Region", value="Bochum")

# Branchen-Info
branch_factor = BRANCH_FACTORS.get(branche, 1.0)
if branch_factor > 1.0:
    st.info(f"💰 {branche}: Multiplikator **×{branch_factor}** (High-Value)")
elif branch_factor < 1.0:
    st.info(f"📉 {branche}: Multiplikator **×{branch_factor}**")

# API Info
st.markdown("""
<div class="api-info">
    <strong>🔌 Powered by Outscraper</strong><br>
    <small>Echte Owner-Response-Daten • Mehr Ergebnisse • Multi-Plattform ready</small>
</div>
""", unsafe_allow_html=True)

# Suchen Button
if st.button("🔍 Businesses suchen", type="primary", use_container_width=True):
    
    if not OUTSCRAPER_API_KEY:
        st.error("Bitte API Key eingeben!")
    else:
        # Phase 1: Businesses finden
        with st.spinner(f"🔍 Suche {branche} in {location}..."):
            businesses = search_businesses_outscraper(
                branche, 
                location, 
                OUTSCRAPER_API_KEY, 
                limit=result_limit
            )
        
        if not businesses:
            st.warning("Keine Ergebnisse gefunden. Versuche eine andere Suche.")
        else:
            st.success(f"✅ {len(businesses)} Businesses gefunden!")
            
            # Phase 2: Reviews analysieren
            results = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, business in enumerate(businesses):
                name = business.get("name", "Unknown")
                status_text.text(f"📊 Analysiere {i+1}/{len(businesses)}: {name}")
                progress_bar.progress((i + 1) / len(businesses))
                
                place_id = business.get("place_id", "")
                address = business.get("full_address", business.get("address", ""))
                rating = business.get("rating", 0)
                review_count = business.get("reviews", business.get("reviews_count", 0))
                maps_url = business.get("google_maps_url", business.get("link", ""))
                phone = business.get("phone", "")
                website = business.get("site", business.get("website", ""))
                
                # Reviews holen
                reviews = []
                if place_id and review_count and review_count > 0:
                    reviews = get_reviews_outscraper(
                        place_id, 
                        OUTSCRAPER_API_KEY, 
                        reviews_limit=reviews_per_business
                    )
                    time.sleep(0.3)
                
                analysis = analyze_reviews_outscraper(reviews)
                
                lead_score, breakdown = calculate_lead_score(
                    rating, 
                    review_count or 0, 
                    analysis["unanswered_pct"],
                    analysis["last_negative_days"],
                    branche
                )
                
                pain_flags = get_pain_flags(
                    rating,
                    analysis["unanswered_pct"],
                    breakdown["factor"],
                    review_count or 0
                )
                
                category, _ = get_score_category(lead_score)
                
                results.append({
                    "Name": name,
                    "Rating": rating or "-",
                    "Reviews": review_count or 0,
                    "Beantwortet": f"{analysis['answered']}/{analysis['total']}",
                    "Unbeantwortet %": f"{analysis['unanswered_pct']:.0f}%",
                    "Lead-Score": lead_score,
                    "Kategorie": category,
                    "Flags": " ".join(pain_flags) if pain_flags else "-",
                    "Telefon": phone or "-",
                    "Website": website or "-",
                    "Adresse": address,
                    "Google Maps": maps_url
                })
            
            progress_bar.empty()
            status_text.empty()
            
            df = pd.DataFrame(results)
            df = df.sort_values("Lead-Score", ascending=False)
            
            # Metriken
            st.divider()
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Businesses", len(df))
            with col2:
                valid_ratings = [r for r in df['Rating'].tolist() if r != "-"]
                avg_rating = sum(valid_ratings) / len(valid_ratings) if valid_ratings else 0
                st.metric("Ø Rating", f"{avg_rating:.1f} ⭐")
            with col3:
                hot_leads = len(df[df["Lead-Score"] >= 70])
                st.metric("🔥 Hot Leads", hot_leads)
            with col4:
                avg_score = df["Lead-Score"].mean()
                st.metric("Ø Score", f"{avg_score:.0f}")
            
            st.divider()
            
            flag_cols = st.columns(4)
            with flag_cols[0]:
                reputation_risk = len([r for r in results if "🚨" in r["Flags"]])
                st.metric("🚨 Reputation Risk", reputation_risk)
            with flag_cols[1]:
                response_problem = len([r for r in results if "⏰" in r["Flags"]])
                st.metric("⏰ Response Problem", response_problem)
            with flag_cols[2]:
                high_value = len([r for r in results if "💰" in r["Flags"]])
                st.metric("💰 High Value", high_value)
            with flag_cols[3]:
                high_volume = len([r for r in results if "📊" in r["Flags"]])
                st.metric("📊 High Volume", high_volume)
            
            st.divider()
            
            st.subheader("📋 Ergebnisse")
            
            st.markdown("🔥 Hot (70+) · 🟡 Warm (50-69) · 🔵 Cold (30-49) · ⚪ Low (0-29)")
            
            def highlight_score(val):
                if isinstance(val, (int, float)):
                    if val >= 70:
                        return 'background-color: #22C55E33; color: #22C55E; font-weight: bold'
                    elif val >= 50:
                        return 'background-color: #F59E0B33; color: #F59E0B; font-weight: bold'
                    elif val >= 30:
                        return 'background-color: #3B82F633; color: #3B82F6; font-weight: bold'
                return ''
            
            display_cols = ["Name", "Rating", "Reviews", "Beantwortet", "Unbeantwortet %", 
                          "Lead-Score", "Kategorie", "Flags", "Telefon"]
            
            styled_df = df[display_cols].style.applymap(highlight_score, subset=['Lead-Score'])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            col1, col2 = st.columns(2)
            
            with col1:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Als CSV exportieren",
                    data=csv,
                    file_name=f"reviewhunter_{branche.lower()}_{location.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col2:
                hot_df = df[df["Lead-Score"] >= 70]
                if len(hot_df) > 0:
                    hot_csv = hot_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label=f"🔥 Nur Hot Leads ({len(hot_df)})",
                        data=hot_csv,
                        file_name=f"reviewhunter_HOT_{branche.lower()}_{location.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    ReviewHunter by ReviewGuard | <a href="https://review-guard.app" target="_blank">review-guard.app</a><br>
    <small>Powered by Outscraper API</small>
</div>
""", unsafe_allow_html=True)

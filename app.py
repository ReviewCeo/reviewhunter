import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import os

# Konfiguration
st.set_page_config(
    page_title="ReviewHunter",
    page_icon="🎯",
    layout="wide"
)

# API Key aus Secrets oder Environment
GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY", os.getenv("GOOGLE_API_KEY", ""))

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
    .pain-flag {
        font-size: 0.9rem;
        margin-right: 4px;
    }
    .metric-card {
        background: #1a1a1a;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #D4A445;
    }
    .legend-item {
        display: inline-block;
        margin-right: 15px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


def search_places(query: str, location: str, api_key: str) -> list:
    """Sucht Businesses via Google Places API"""
    
    url = "https://places.googleapis.com/v1/places:searchText"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.googleMapsUri,places.primaryType"
    }
    
    data = {
        "textQuery": f"{query} in {location}",
        "languageCode": "de",
        "maxResultCount": 20
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result.get("places", [])
    except Exception as e:
        st.error(f"API Fehler: {str(e)}")
        return []


def get_place_reviews(place_id: str, api_key: str) -> dict:
    """Holt Reviews für einen Ort"""
    
    url = f"https://places.googleapis.com/v1/{place_id}"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "id,displayName,rating,userRatingCount,reviews"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {}


def analyze_reviews(reviews: list) -> dict:
    """Analysiert Reviews auf Antworten und Aktualität"""
    
    if not reviews:
        return {
            "total": 0,
            "answered": 0,
            "unanswered": 0,
            "unanswered_pct": 100,
            "avg_rating": 0,
            "recent_negative": 0,
            "last_negative_days": 999
        }
    
    total = len(reviews)
    answered = 0
    recent_negative = 0
    ratings = []
    last_negative_days = 999
    
    now = datetime.now()
    
    for review in reviews:
        # Check for owner response
        if review.get("ownerResponse"):
            answered += 1
        
        # Get rating
        rating = review.get("rating", 0)
        ratings.append(rating)
        
        # Count recent negative (1-3 stars) and track days
        if rating <= 3:
            recent_negative += 1
            # Try to get review date
            publish_time = review.get("publishTime", "")
            if publish_time:
                try:
                    review_date = datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
                    days_ago = (now - review_date.replace(tzinfo=None)).days
                    if days_ago < last_negative_days:
                        last_negative_days = days_ago
                except:
                    pass
    
    unanswered = total - answered
    unanswered_pct = (unanswered / total * 100) if total > 0 else 0
    avg_rating = sum(ratings) / len(ratings) if ratings else 0
    
    return {
        "total": total,
        "answered": answered,
        "unanswered": unanswered,
        "unanswered_pct": unanswered_pct,
        "avg_rating": avg_rating,
        "recent_negative": recent_negative,
        "last_negative_days": last_negative_days
    }


def calculate_lead_score(rating: float, review_count: int, unanswered_pct: float, 
                         last_negative_days: int, branche: str) -> tuple:
    """
    Berechnet Lead-Score v2.1 (0-100+)
    
    Returns: (score, breakdown)
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
        f2 = 12  # Kein Rating = mittleres Potenzial
    
    # Rating-Gewicht reduzieren bei wenigen Reviews
    if review_count < 10:
        f2 = int(f2 * 0.5)
    
    # Faktor 3: Volumen/Relevanz (max 20 Punkte)
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
        f3 = 0  # 0-4 Reviews = kein ernsthafter Case
    
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
    
    # Raw Score
    raw_score = f1 + f2 + f3 + f4
    
    # Faktor 5: Branchen-Multiplikator
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
    
    # 🚨 Reputation at Risk - Rating unter 4.0
    if rating and rating < 4.0:
        flags.append("🚨")
    
    # ⏰ Response Problem - Über 50% unbeantwortet
    if unanswered_pct > 50:
        flags.append("⏰")
    
    # 💰 High Value - Branchen-Faktor über 1.2
    if branch_factor >= 1.2:
        flags.append("💰")
    
    # 📊 Volume - Viele Reviews
    if review_count >= 50:
        flags.append("📊")
    
    return flags


def get_score_category(score: int) -> tuple:
    """Gibt Kategorie und Emoji für Score zurück"""
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

# Sidebar für Einstellungen
with st.sidebar:
    st.header("⚙️ Einstellungen")
    
    # API Key Input (falls nicht in secrets)
    if not GOOGLE_API_KEY:
        api_key_input = st.text_input("Google API Key", type="password")
        if api_key_input:
            GOOGLE_API_KEY = api_key_input
    else:
        st.success("✅ API Key geladen")
    
    st.divider()
    
    st.header("📊 Lead-Score Erklärung")
    st.markdown("""
    **70-100:** 🔥 Heißer Lead  
    **50-69:** 🟡 Warmer Lead  
    **30-49:** 🔵 Kalter Lead  
    **0-29:** ⚪ Kein Lead
    
    **Faktoren:**
    - Antwortverhalten (35%)
    - Rating-Problem (25%)
    - Review-Volumen (20%)
    - Aktualität (10%)
    - Branchen-Multiplikator
    """)
    
    st.divider()
    
    st.header("🏷️ Pain-Flags")
    st.markdown("""
    🚨 **Reputation at Risk**  
    Rating unter 4.0
    
    ⏰ **Response Problem**  
    Über 50% unbeantwortet
    
    💰 **High Value**  
    Branche mit hohem Budget
    
    📊 **High Volume**  
    50+ Reviews
    """)

# Hauptbereich
col1, col2 = st.columns([1, 1])

with col1:
    branche = st.selectbox(
        "Branche",
        ["Friseur", "Restaurant", "Zahnarzt", "Kosmetik", "Fitness", "Physiotherapie", "Handwerker", "Autohaus", "Hotel", "Café", "Arzt", "Anwalt", "Steuerberater"]
    )

with col2:
    location = st.text_input("Stadt / Region", value="Hattingen")

# Branchen-Info anzeigen
branch_factor = BRANCH_FACTORS.get(branche, 1.0)
if branch_factor > 1.0:
    st.info(f"💰 {branche}: Branchen-Multiplikator **×{branch_factor}** (höheres Budget)")
elif branch_factor < 1.0:
    st.info(f"📉 {branche}: Branchen-Multiplikator **×{branch_factor}** (kleineres Budget)")

# Suchen Button
if st.button("🔍 Businesses suchen", type="primary", use_container_width=True):
    
    if not GOOGLE_API_KEY:
        st.error("Bitte API Key eingeben!")
    else:
        with st.spinner(f"Suche {branche} in {location}..."):
            
            # Suche starten
            places = search_places(branche, location, GOOGLE_API_KEY)
            
            if not places:
                st.warning("Keine Ergebnisse gefunden. Versuche eine andere Suche.")
            else:
                st.success(f"✅ {len(places)} Businesses gefunden!")
                
                # Daten sammeln
                results = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, place in enumerate(places):
                    status_text.text(f"Analysiere {i+1}/{len(places)}: {place.get('displayName', {}).get('text', 'Unknown')}")
                    progress_bar.progress((i + 1) / len(places))
                    
                    place_id = place.get("id", "")
                    name = place.get("displayName", {}).get("text", "Unknown")
                    address = place.get("formattedAddress", "")
                    rating = place.get("rating", 0)
                    review_count = place.get("userRatingCount", 0)
                    maps_url = place.get("googleMapsUri", "")
                    
                    # Reviews holen (wenn möglich)
                    place_details = get_place_reviews(place_id, GOOGLE_API_KEY)
                    reviews = place_details.get("reviews", [])
                    
                    # Analyse
                    analysis = analyze_reviews(reviews)
                    
                    # Lead Score berechnen (v2.1)
                    lead_score, breakdown = calculate_lead_score(
                        rating, 
                        review_count, 
                        analysis["unanswered_pct"],
                        analysis["last_negative_days"],
                        branche
                    )
                    
                    # Pain Flags
                    pain_flags = get_pain_flags(
                        rating,
                        analysis["unanswered_pct"],
                        breakdown["factor"],
                        review_count
                    )
                    
                    # Kategorie
                    category, _ = get_score_category(lead_score)
                    
                    results.append({
                        "Name": name,
                        "Rating": rating,
                        "Reviews": review_count,
                        "Unbeantwortet": f"{analysis['unanswered']}/{analysis['total']}",
                        "Unbeantwortet %": f"{analysis['unanswered_pct']:.0f}%",
                        "Lead-Score": lead_score,
                        "Kategorie": category,
                        "Flags": " ".join(pain_flags) if pain_flags else "-",
                        "Adresse": address,
                        "Google Maps": maps_url
                    })
                
                progress_bar.empty()
                status_text.empty()
                
                # DataFrame erstellen und sortieren
                df = pd.DataFrame(results)
                df = df.sort_values("Lead-Score", ascending=False)
                
                # Metriken anzeigen
                st.divider()
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Businesses", len(df))
                with col2:
                    st.metric("Ø Rating", f"{df['Rating'].mean():.1f} ⭐")
                with col3:
                    hot_leads = len(df[df["Lead-Score"] >= 70])
                    st.metric("🔥 Heiße Leads", hot_leads)
                with col4:
                    avg_score = df["Lead-Score"].mean()
                    st.metric("Ø Lead-Score", f"{avg_score:.0f}")
                
                # Pain-Flag Zusammenfassung
                st.divider()
                
                flag_cols = st.columns(4)
                with flag_cols[0]:
                    reputation_risk = len([r for r in results if "🚨" in r["Flags"]])
                    st.metric("🚨 Reputation at Risk", reputation_risk)
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
                
                # Tabelle anzeigen
                st.subheader("📋 Ergebnisse")
                
                # Legende
                st.markdown("""
                <div style="margin-bottom: 10px;">
                    <span class="legend-item">🔥 Hot (70+)</span>
                    <span class="legend-item">🟡 Warm (50-69)</span>
                    <span class="legend-item">🔵 Cold (30-49)</span>
                    <span class="legend-item">⚪ Low (0-29)</span>
                </div>
                """, unsafe_allow_html=True)
                
                # Styling für Tabelle
                def highlight_score(val):
                    if isinstance(val, (int, float)):
                        if val >= 70:
                            return 'background-color: #22C55E33; color: #22C55E; font-weight: bold'
                        elif val >= 50:
                            return 'background-color: #F59E0B33; color: #F59E0B; font-weight: bold'
                        elif val >= 30:
                            return 'background-color: #3B82F633; color: #3B82F6; font-weight: bold'
                    return ''
                
                styled_df = df.style.applymap(highlight_score, subset=['Lead-Score'])
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                
                # Export
                st.divider()
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Als CSV exportieren",
                    data=csv,
                    file_name=f"reviewhunter_{branche.lower()}_{location.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    ReviewHunter by ReviewGuard | <a href="https://review-guard.app" target="_blank">review-guard.app</a>
</div>
""", unsafe_allow_html=True)

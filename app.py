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
    .score-high { color: #22C55E; font-weight: bold; }
    .score-medium { color: #F59E0B; font-weight: bold; }
    .score-low { color: #EF4444; font-weight: bold; }
    .metric-card {
        background: #1a1a1a;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #D4A445;
    }
</style>
""", unsafe_allow_html=True)


def search_places(query: str, location: str, api_key: str) -> list:
    """Sucht Businesses via Google Places API"""
    
    # Text Search API (New)
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


def calculate_lead_score(rating: float, review_count: int, unanswered_pct: float) -> int:
    """
    Berechnet Lead-Score (0-100)
    Höher = besserer Lead (= schlechteres Review-Management)
    """
    score = 0
    
    # Rating Score (max 35 Punkte)
    # Schlechteres Rating = höherer Score
    if rating:
        if rating < 3.5:
            score += 35
        elif rating < 4.0:
            score += 25
        elif rating < 4.3:
            score += 15
        elif rating < 4.5:
            score += 8
        else:
            score += 0
    else:
        score += 20  # Kein Rating = Potenzial
    
    # Review Count Score (max 30 Punkte)
    # Mehr Reviews = mehr Potenzial
    if review_count >= 100:
        score += 30
    elif review_count >= 50:
        score += 25
    elif review_count >= 20:
        score += 20
    elif review_count >= 10:
        score += 15
    elif review_count >= 5:
        score += 10
    else:
        score += 5
    
    # Unanswered Percentage Score (max 35 Punkte)
    # Mehr unbeantwortet = höherer Score
    score += int(unanswered_pct * 0.35)
    
    return min(100, score)


def analyze_reviews(reviews: list) -> dict:
    """Analysiert Reviews auf Antworten"""
    
    if not reviews:
        return {
            "total": 0,
            "answered": 0,
            "unanswered": 0,
            "unanswered_pct": 100,
            "avg_rating": 0,
            "recent_negative": 0
        }
    
    total = len(reviews)
    answered = sum(1 for r in reviews if r.get("authorAttribution", {}).get("displayName") and 
                   "ownerResponse" in str(r) or "reply" in str(r).lower())
    
    # Einfachere Logik: Prüfe ob 'authorAttribution' eine Antwort hat
    answered = 0
    recent_negative = 0
    ratings = []
    
    for review in reviews:
        # Check for owner response
        if review.get("ownerResponse"):
            answered += 1
        
        # Get rating
        rating = review.get("rating", 0)
        ratings.append(rating)
        
        # Count recent negative (1-3 stars)
        if rating <= 3:
            recent_negative += 1
    
    unanswered = total - answered
    unanswered_pct = (unanswered / total * 100) if total > 0 else 0
    avg_rating = sum(ratings) / len(ratings) if ratings else 0
    
    return {
        "total": total,
        "answered": answered,
        "unanswered": unanswered,
        "unanswered_pct": unanswered_pct,
        "avg_rating": avg_rating,
        "recent_negative": recent_negative
    }


def get_score_color(score: int) -> str:
    """Gibt CSS-Klasse für Score zurück"""
    if score >= 70:
        return "score-high"
    elif score >= 40:
        return "score-medium"
    else:
        return "score-low"


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
    **40-69:** 🟡 Guter Lead  
    **0-39:** 🔵 Niedriger Score
    
    **Faktoren:**
    - Rating (< 4.0 = mehr Punkte)
    - Anzahl Reviews
    - Unbeantwortete Reviews
    """)

# Hauptbereich
col1, col2 = st.columns([1, 1])

with col1:
    branche = st.selectbox(
        "Branche",
        ["Friseur", "Restaurant", "Zahnarzt", "Kosmetik", "Fitness", "Physiotherapie", "Handwerker", "Autohaus", "Hotel", "Café"]
    )

with col2:
    location = st.text_input("Stadt / Region", value="Hattingen")

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
                    
                    # Lead Score berechnen
                    lead_score = calculate_lead_score(
                        rating, 
                        review_count, 
                        analysis["unanswered_pct"]
                    )
                    
                    results.append({
                        "Name": name,
                        "Rating": rating,
                        "Reviews": review_count,
                        "Unbeantwortet": f"{analysis['unanswered']}/{analysis['total']}",
                        "Unbeantwortet %": f"{analysis['unanswered_pct']:.0f}%",
                        "Lead-Score": lead_score,
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
                
                st.divider()
                
                # Tabelle anzeigen
                st.subheader("📋 Ergebnisse")
                
                # Styling für Tabelle
                def highlight_score(val):
                    if isinstance(val, (int, float)):
                        if val >= 70:
                            return 'background-color: #22C55E33; color: #22C55E'
                        elif val >= 40:
                            return 'background-color: #F59E0B33; color: #F59E0B'
                    return ''
                
                styled_df = df.style.applymap(highlight_score, subset=['Lead-Score'])
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                
                # Export
                st.divider()
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Als CSV exportieren",
                    data=csv,
                    file_name=f"reviewscout_{branche.lower()}_{location.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
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

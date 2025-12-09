# 🎯 ReviewHunter

**Finde Businesses mit schlechtem Review-Management**

ReviewHunter analysiert Google-Bewertungen und berechnet einen Lead-Score für potenzielle Kunden.

## Features

- 🔍 Suche nach Branche + Stadt
- ⭐ Rating & Review-Analyse
- 📊 Lead-Score Berechnung (0-100)
- 📥 CSV Export
- 🎨 Dark Mode UI

## Lead-Score Erklärung

| Score | Bedeutung |
|-------|-----------|
| 70-100 | 🔥 Heißer Lead - schlechtes Review-Management |
| 40-69 | 🟡 Guter Lead - Verbesserungspotenzial |
| 0-39 | 🔵 Niedriger Score - gutes Management |

**Faktoren:**
- Rating unter 4.0 = mehr Punkte
- Viele Reviews = mehr Potenzial
- Unbeantwortete Reviews = mehr Punkte

## Setup

### 1. Dependencies installieren
```bash
pip install -r requirements.txt
```

### 2. API Key konfigurieren
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Dann API Key eintragen
```

### 3. App starten
```bash
streamlit run app.py
```

## Google Places API

Du brauchst einen Google Cloud Account mit aktivierter Places API (New).

1. Google Cloud Console → Neues Projekt
2. Places API (New) aktivieren
3. API Key erstellen
4. In `.streamlit/secrets.toml` eintragen

**Kosten:** ~$17 pro 1000 Suchen (Text Search) + $5 pro 1000 Place Details

## Deployment

### Streamlit Cloud (kostenlos)
1. Repo auf GitHub pushen
2. streamlit.io → New App → Repo auswählen
3. Secrets in Streamlit Cloud Settings eintragen

### Railway (~$5/Monat)
```bash
railway login
railway init
railway up
```

## Roadmap

- [ ] Mehr Branchen
- [ ] Automatische Reports
- [ ] E-Mail Benachrichtigungen
- [ ] Premium Tier mit mehr Features
- [ ] API für externe Integration

---

**Teil von [ReviewGuard](https://review-guard.app)** 🛡️

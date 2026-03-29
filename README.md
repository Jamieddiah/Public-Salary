# 🇸🇳 SIRH — Système d'Information des Ressources Humaines

**Administration Publique Sénégalaise**

Application de gestion des ressources humaines et de la paie pour l'administration publique sénégalaise. Gère 250 000+ agents répartis dans 30+ ministères avec 5 statuts différents.

## Prérequis

- **Python 3.10+** (testé avec 3.12)
- **pip** (gestionnaire de paquets Python)

## Installation

```bash
# 1. Installer les dépendances
pip3 install reportlab pillow

# 2. Lancer le serveur (la base se crée automatiquement)
python3 server.py

# 3. Ouvrir dans le navigateur
open http://localhost:8080
```

## Comptes de démonstration

| Login | Mot de passe | Rôle | Périmètre |
|-------|-------------|------|-----------|
| `admin` | `admin123` | Administrateur | Accès total |
| `rh_mfin` | `rh123` | Gestionnaire RH | Ministère des Finances |
| `rh_msant` | `rh123` | Gestionnaire RH | Ministère de la Santé |
| `rh_meduc` | `rh123` | Gestionnaire RH | Éducation Nationale |
| `rh_farme` | `rh123` | Gestionnaire RH | Forces Armées |

## Pages de l'application

| Page | Description |
|------|-------------|
| 📊 **Tableau de bord** | KPIs, répartition par statut, derniers agents |
| 🏛️ **Organigramme** | Arbre interactif Ministère → DG → Direction → Service |
| 👥 **Agents** | Liste paginée avec filtres, CRUD complet |
| 📋 **Grilles indiciaires** | Grilles par statut avec salaire de base calculé |
| 📝 **Éléments variables** | Saisie et validation des EVS (workflow 3 étapes) |
| 💰 **Calcul de paie** | Bulletin individuel ou batch, avec détail complet |
| 📈 **Masse salariale** | Rapport agrégé par ministère ou direction |
| ⚙️ **Paramètres** | Valeur du point d'indice (admin uniquement) |

## 5 statuts gérés

- **Titulaire** — Fonctionnaires (IPRES standard : 5,6% / 8,4%)
- **Contractuel** — Contractuels de l'État
- **Militaire** — Forces armées (FCRPS : 4% / 6%)
- **Gendarmerie** — Gendarmes (FCRPS)
- **Police** — Forces de police (FCRPS)

## Moteur de paie

Le moteur calcule automatiquement :
- Salaire de base = Indice × Valeur du point (475 FCFA)
- Primes statutaires (logement, transport, représentation, technicité, etc.)
- Cotisations IPRES/FCRPS, CSS, CFCE
- IR selon le barème progressif sénégalais (avec abattement 30% et parts fiscales)
- TRIMF
- Éléments variables (heures sup, missions, primes, retenues)

## Structure des fichiers

```
sirh/
├── server.py                     # Serveur HTTP + routes API
├── sirh.db                       # Base SQLite (créée automatiquement)
├── database/
│   ├── __init__.py
│   ├── schema.py                 # Schéma + données de démo
│   ├── moteur_paie.py            # Moteur de calcul de paie
│   └── pdf_generator.py          # Génération bulletins PDF
├── static/
│   └── index.html                # Application SPA complète
├── exports/                      # Bulletins PDF générés
└── README.md
```

## Stack technique (MVP)

| Composant | Technologie |
|-----------|------------|
| Backend | Python 3.12 — http.server (stdlib) |
| Base de données | SQLite 3 |
| Frontend | HTML5 / CSS3 / JavaScript vanilla |
| Génération PDF | ReportLab |
| Authentification | Sessions en mémoire (SHA-256) |

## API REST

Toutes les routes sous `/api/` avec authentification Bearer token.

- `POST /api/auth/login` — Connexion
- `GET /api/stats` — Dashboard KPIs
- `GET /api/organigramme` — Arbre organisationnel
- `GET /api/agents` — Liste agents (filtres, pagination)
- `POST /api/agents` — Créer agent
- `GET /api/grilles` — Grilles indiciaires
- `GET/POST /api/evs` — Éléments variables
- `POST /api/bulletins/calculer` — Calcul bulletin
- `POST /api/bulletins/batch` — Calcul batch
- `GET /api/rapport/masse-salariale` — Rapport agrégé

---

*Projet MVP — Version test locale. Version production : PostgreSQL + FastAPI + React + Docker.*

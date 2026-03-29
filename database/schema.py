"""
SIRH — Schéma de base de données SQLite et données de démonstration
Administration Publique Sénégalaise
"""

import sqlite3
import hashlib
import os
import random

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sirh.db')


def get_db(db_path=None):
    """Obtenir une connexion à la base de données."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password):
    """Hacher un mot de passe avec SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def init_db(db_path=None):
    """Initialiser la base de données : création des tables et seed."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # ── Tables organisationnelles ──────────────────────────────────────
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS ministeres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL,
        ministre TEXT,
        actif INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS directions_generales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ministere_id INTEGER NOT NULL,
        code TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL,
        directeur TEXT,
        actif INTEGER DEFAULT 1,
        FOREIGN KEY (ministere_id) REFERENCES ministeres(id)
    );

    CREATE TABLE IF NOT EXISTS directions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        direction_generale_id INTEGER NOT NULL,
        code TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL,
        actif INTEGER DEFAULT 1,
        FOREIGN KEY (direction_generale_id) REFERENCES directions_generales(id)
    );

    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        direction_id INTEGER NOT NULL,
        code TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL,
        chef_service TEXT,
        actif INTEGER DEFAULT 1,
        FOREIGN KEY (direction_id) REFERENCES directions(id)
    );

    -- ── Agents ─────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matricule TEXT UNIQUE NOT NULL,
        nom TEXT NOT NULL,
        prenom TEXT NOT NULL,
        date_naissance TEXT,
        sexe TEXT CHECK(sexe IN ('M','F')),
        statut TEXT NOT NULL CHECK(statut IN ('titulaire','contractuel','militaire','gendarmerie','police')),
        corps TEXT NOT NULL,
        grade TEXT NOT NULL,
        echelon INTEGER NOT NULL DEFAULT 1,
        indice INTEGER NOT NULL,
        situation_matrimoniale TEXT DEFAULT 'Célibataire'
            CHECK(situation_matrimoniale IN ('Célibataire','Marié(e)','Divorcé(e)','Veuf(ve)')),
        nb_enfants INTEGER DEFAULT 0,
        service_id INTEGER,
        date_entree TEXT,
        actif INTEGER DEFAULT 1,
        FOREIGN KEY (service_id) REFERENCES services(id)
    );

    -- ── Grilles indiciaires ────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS grilles_indiciaires (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        statut TEXT NOT NULL,
        corps TEXT NOT NULL,
        grade TEXT NOT NULL,
        echelon INTEGER NOT NULL,
        indice INTEGER NOT NULL
    );

    -- ── Primes statutaires ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS primes_statutaires (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        libelle TEXT NOT NULL,
        statut TEXT NOT NULL,
        corps_requis TEXT,
        mode_calcul TEXT NOT NULL CHECK(mode_calcul IN ('fixe','pourcentage')),
        taux_ou_montant REAL NOT NULL,
        imposable INTEGER DEFAULT 0
    );

    -- ── Types d'éléments variables ─────────────────────────────────────
    CREATE TABLE IF NOT EXISTS types_evs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        libelle TEXT NOT NULL,
        type_evs TEXT NOT NULL CHECK(type_evs IN ('gain','retenue')),
        mode_calcul TEXT NOT NULL CHECK(mode_calcul IN ('horaire','journalier','fixe')),
        imposable INTEGER DEFAULT 1,
        plafond REAL
    );

    -- ── Éléments variables saisis ──────────────────────────────────────
    CREATE TABLE IF NOT EXISTS elements_variables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        type_evs_id INTEGER NOT NULL,
        periode TEXT NOT NULL,
        quantite REAL DEFAULT 0,
        montant REAL DEFAULT 0,
        statut_validation TEXT DEFAULT 'en_attente'
            CHECK(statut_validation IN ('en_attente','valide','rejete','visa')),
        validateur TEXT,
        commentaire TEXT,
        date_creation TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (agent_id) REFERENCES agents(id),
        FOREIGN KEY (type_evs_id) REFERENCES types_evs(id)
    );

    -- ── Paramètres de paie ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS parametres_paie (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        libelle TEXT NOT NULL,
        valeur REAL NOT NULL,
        periode TEXT NOT NULL,
        actif INTEGER DEFAULT 1
    );

    -- ── Bulletins de paie ──────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS bulletins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        periode TEXT NOT NULL,
        salaire_base REAL DEFAULT 0,
        total_primes REAL DEFAULT 0,
        total_evs_gains REAL DEFAULT 0,
        total_evs_retenues REAL DEFAULT 0,
        salaire_brut_imposable REAL DEFAULT 0,
        salaire_brut_non_imposable REAL DEFAULT 0,
        ipres_rg_emp REAL DEFAULT 0,
        ipres_rc_emp REAL DEFAULT 0,
        ir_mensuel REAL DEFAULT 0,
        trimf REAL DEFAULT 0,
        total_retenues REAL DEFAULT 0,
        salaire_net REAL DEFAULT 0,
        charges_patronales_ipres_rg REAL DEFAULT 0,
        charges_patronales_ipres_rc REAL DEFAULT 0,
        charges_patronales_css_af REAL DEFAULT 0,
        charges_patronales_css_at REAL DEFAULT 0,
        charges_patronales_cfce REAL DEFAULT 0,
        total_charges_patronales REAL DEFAULT 0,
        cout_employeur REAL DEFAULT 0,
        date_calcul TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    );

    -- ── Lignes de bulletin ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS lignes_bulletin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bulletin_id INTEGER NOT NULL,
        rubrique_code TEXT NOT NULL,
        rubrique_libelle TEXT NOT NULL,
        base REAL DEFAULT 0,
        taux REAL DEFAULT 0,
        montant_gain REAL DEFAULT 0,
        montant_retenue REAL DEFAULT 0,
        FOREIGN KEY (bulletin_id) REFERENCES bulletins(id)
    );

    -- ── Utilisateurs ───────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS utilisateurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE NOT NULL,
        mot_de_passe_hash TEXT NOT NULL,
        nom TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','gestionnaire','controleur','auditeur')),
        ministere_id INTEGER,
        actif INTEGER DEFAULT 1,
        FOREIGN KEY (ministere_id) REFERENCES ministeres(id)
    );

    -- ── Journal d'audit ────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS journal_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utilisateur_id INTEGER,
        action TEXT NOT NULL,
        table_cible TEXT,
        enregistrement_id INTEGER,
        details TEXT,
        date_action TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
    );
    """)

    conn.commit()

    # Vérifier si les données existent déjà
    count = cur.execute("SELECT COUNT(*) FROM ministeres").fetchone()[0]
    if count == 0:
        seed_data(conn)

    conn.close()
    print(f"✅ Base de données initialisée : {path}")


def seed_data(conn):
    """Peupler la base avec les données de démonstration."""
    cur = conn.cursor()

    # ══════════════════════════════════════════════════════════════════
    # 1. MINISTÈRES (5)
    # ══════════════════════════════════════════════════════════════════
    ministeres = [
        ('MIN_FIN', 'Ministère des Finances et du Budget', 'Mamadou Moustapha Ba'),
        ('MIN_SANT', 'Ministère de la Santé et de l\'Action Sociale', 'Marie Khemesse Ngom Ndiaye'),
        ('MIN_EDUC', 'Ministère de l\'Éducation Nationale', 'Cheikh Oumar Anne'),
        ('MIN_JUST', 'Ministère de la Justice', 'Ismaïla Madior Fall'),
        ('MIN_FARM', 'Ministère des Forces Armées', 'Sidiki Kaba'),
    ]
    cur.executemany("INSERT INTO ministeres (code, nom, ministre) VALUES (?, ?, ?)", ministeres)

    # ══════════════════════════════════════════════════════════════════
    # 2. DIRECTIONS GÉNÉRALES (9)
    # ══════════════════════════════════════════════════════════════════
    dgs = [
        (1, 'DGB',   'Direction Générale du Budget',                          'Abdoulaye Daouda Diallo'),
        (1, 'DGID',  'Direction Générale des Impôts et Domaines',             'Bassirou Samba Niasse'),
        (1, 'DGTCP', 'Direction Générale du Trésor et de la Comptabilité Publique', 'Cheikh Tidiane Diop'),
        (2, 'DGAS',  'Direction Générale de l\'Action Sanitaire',             'Dr. Boly Diop'),
        (2, 'DGSF',  'Direction Générale de la Santé de la Famille',          'Dr. Aïssatou Sow'),
        (3, 'DGEF',  'Direction Générale de l\'Enseignement Fondamental',     'Mamadou Talla'),
        (3, 'DGES',  'Direction Générale de l\'Enseignement Supérieur',       'Pr. Moussa Baldé'),
        (4, 'DGAJ',  'Direction Générale de l\'Administration Judiciaire',    'Ousmane Diagne'),
        (5, 'DGFAR', 'Direction Générale des Forces Armées et de la Réserve', 'Général Mbaye Cissé'),
    ]
    cur.executemany(
        "INSERT INTO directions_generales (ministere_id, code, nom, directeur) VALUES (?, ?, ?, ?)", dgs
    )

    # ══════════════════════════════════════════════════════════════════
    # 3. DIRECTIONS (10)
    # ══════════════════════════════════════════════════════════════════
    directions = [
        (1, 'DB',    'Direction du Budget'),
        (2, 'DI',    'Direction des Impôts'),
        (3, 'DTCP',  'Direction du Trésor'),
        (4, 'DAS',   'Direction de l\'Action Sanitaire'),
        (5, 'DSF',   'Direction de la Santé Familiale'),
        (6, 'DEF',   'Direction de l\'Enseignement Fondamental'),
        (7, 'DES',   'Direction de l\'Enseignement Supérieur'),
        (8, 'DAJ',   'Direction de l\'Administration Judiciaire'),
        (9, 'DFAR',  'Direction des Forces Armées'),
        (9, 'DRES',  'Direction de la Réserve'),
    ]
    cur.executemany(
        "INSERT INTO directions (direction_generale_id, code, nom) VALUES (?, ?, ?)", directions
    )

    # ══════════════════════════════════════════════════════════════════
    # 4. SERVICES (10)
    # ══════════════════════════════════════════════════════════════════
    services = [
        (1,  'SRH_FIN',  'Service RH — Budget',               'Fatou Diop'),
        (2,  'SRH_IMP',  'Service RH — Impôts',               'Ibrahima Seck'),
        (3,  'SRH_TRE',  'Service RH — Trésor',               'Aminata Fall'),
        (4,  'SRH_SAN',  'Service RH — Action Sanitaire',     'Dr. Oumar Sy'),
        (5,  'SRH_FAM',  'Service RH — Santé Familiale',      'Mariama Ba'),
        (6,  'SRH_ENF',  'Service RH — Enseignement Fondamental', 'Moussa Ndiaye'),
        (7,  'SRH_SUP',  'Service RH — Enseignement Supérieur',   'Aïda Mbaye'),
        (8,  'SRH_JUS',  'Service RH — Justice',              'Lamine Touré'),
        (9,  'SRH_ARM',  'Service RH — Forces Armées',        'Colonel Sall'),
        (10, 'SRH_RES',  'Service RH — Réserve',              'Commandant Diagne'),
    ]
    cur.executemany(
        "INSERT INTO services (direction_id, code, nom, chef_service) VALUES (?, ?, ?, ?)", services
    )

    # ══════════════════════════════════════════════════════════════════
    # 5. GRILLES INDICIAIRES
    # ══════════════════════════════════════════════════════════════════
    grilles = [
        # Titulaires
        ('titulaire', 'Administrateur Civil', 'Grade A1', 1, 300),
        ('titulaire', 'Administrateur Civil', 'Grade A1', 2, 330),
        ('titulaire', 'Administrateur Civil', 'Grade A1', 3, 360),
        ('titulaire', 'Administrateur Civil', 'Grade A2', 1, 400),
        ('titulaire', 'Administrateur Civil', 'Grade A2', 2, 440),
        ('titulaire', 'Administrateur Civil', 'Grade A2', 3, 480),
        ('titulaire', 'Médecin', 'Grade A1', 1, 450),
        ('titulaire', 'Médecin', 'Grade A1', 2, 490),
        ('titulaire', 'Médecin', 'Grade A1', 3, 530),
        ('titulaire', 'Médecin', 'Grade A2', 1, 550),
        ('titulaire', 'Médecin', 'Grade A2', 2, 600),
        ('titulaire', 'Médecin', 'Grade A2', 3, 650),
        ('titulaire', 'Instituteur', 'Grade B1', 1, 200),
        ('titulaire', 'Instituteur', 'Grade B1', 2, 220),
        ('titulaire', 'Instituteur', 'Grade B1', 3, 240),
        ('titulaire', 'Instituteur', 'Grade B2', 1, 250),
        ('titulaire', 'Instituteur', 'Grade B2', 2, 275),
        ('titulaire', 'Instituteur', 'Grade B2', 3, 300),
        ('titulaire', 'Agent Administratif', 'Grade C1', 1, 150),
        ('titulaire', 'Agent Administratif', 'Grade C1', 2, 165),
        ('titulaire', 'Agent Administratif', 'Grade C1', 3, 180),
        ('titulaire', 'Agent Administratif', 'Grade C2', 1, 180),
        ('titulaire', 'Agent Administratif', 'Grade C2', 2, 200),
        ('titulaire', 'Agent Administratif', 'Grade C2', 3, 220),
        # Contractuels
        ('contractuel', 'Contractuel', 'Catégorie I', 1, 350),
        ('contractuel', 'Contractuel', 'Catégorie I', 2, 380),
        ('contractuel', 'Contractuel', 'Catégorie II', 1, 280),
        ('contractuel', 'Contractuel', 'Catégorie II', 2, 310),
        ('contractuel', 'Contractuel', 'Catégorie III', 1, 200),
        ('contractuel', 'Contractuel', 'Catégorie III', 2, 220),
        # Militaires
        ('militaire', 'Officier', 'Colonel', 1, 600),
        ('militaire', 'Officier', 'Colonel', 2, 640),
        ('militaire', 'Officier', 'Capitaine', 1, 400),
        ('militaire', 'Officier', 'Capitaine', 2, 430),
        ('militaire', 'Officier', 'Lieutenant', 1, 340),
        ('militaire', 'Officier', 'Lieutenant', 2, 360),
        ('militaire', 'Sous-Officier', 'Adjudant', 1, 250),
        ('militaire', 'Sous-Officier', 'Adjudant', 2, 270),
        ('militaire', 'Sous-Officier', 'Sergent', 1, 200),
        ('militaire', 'Sous-Officier', 'Sergent', 2, 215),
        # Gendarmerie
        ('gendarmerie', 'Officier', 'Colonel', 1, 620),
        ('gendarmerie', 'Officier', 'Colonel', 2, 660),
        ('gendarmerie', 'Officier', 'Capitaine', 1, 410),
        ('gendarmerie', 'Officier', 'Capitaine', 2, 440),
        ('gendarmerie', 'Sous-Officier', 'Adjudant', 1, 260),
        ('gendarmerie', 'Sous-Officier', 'Adjudant', 2, 280),
        ('gendarmerie', 'Sous-Officier', 'Gendarme', 1, 180),
        ('gendarmerie', 'Sous-Officier', 'Gendarme', 2, 195),
        # Police
        ('police', 'Officier', 'Commissaire', 1, 430),
        ('police', 'Officier', 'Commissaire', 2, 460),
        ('police', 'Officier', 'Inspecteur', 1, 320),
        ('police', 'Officier', 'Inspecteur', 2, 345),
        ('police', 'Sous-Officier', 'Brigadier', 1, 220),
        ('police', 'Sous-Officier', 'Brigadier', 2, 240),
        ('police', 'Sous-Officier', 'Gardien de la Paix', 1, 180),
        ('police', 'Sous-Officier', 'Gardien de la Paix', 2, 195),
    ]
    cur.executemany(
        "INSERT INTO grilles_indiciaires (statut, corps, grade, echelon, indice) VALUES (?, ?, ?, ?, ?)",
        grilles
    )

    # ══════════════════════════════════════════════════════════════════
    # 6. PRIMES STATUTAIRES
    # ══════════════════════════════════════════════════════════════════
    primes = [
        ('IND_LOG',    'Indemnité de Logement',           'titulaire',    None,      'fixe',       40000,  0),
        ('IND_TRANS',  'Indemnité de Transport',          'titulaire',    None,      'fixe',       26000,  0),
        ('IND_REP',    'Indemnité de Représentation',     'titulaire',    None,      'pourcentage', 10,    0),
        ('PRIME_TEC',  'Prime de Technicité',             'titulaire',    None,      'pourcentage', 15,    1),
        ('IND_MED',    'Indemnité Médicale Spéciale',     'titulaire',    'Médecin', 'fixe',       80000,  0),
        ('IND_CONT',   'Indemnité de Sujétion Contractuel','contractuel', None,      'pourcentage', 20,    1),
        ('SOLDE_OP',   'Prime Opérationnelle',            'militaire',    None,      'pourcentage', 30,    1),
        ('RATION',     'Ration Alimentaire',              'militaire',    None,      'fixe',       15000,  0),
        ('PRIME_RSQ',  'Prime de Risque',                 'militaire',    None,      'pourcentage', 20,    0),
        ('IND_GEND',   'Indemnité de Gendarmerie',        'gendarmerie',  None,      'pourcentage', 35,    0),
        ('IND_POL',    'Indemnité de Police',             'police',       None,      'pourcentage', 30,    0),
    ]
    cur.executemany(
        """INSERT INTO primes_statutaires
           (code, libelle, statut, corps_requis, mode_calcul, taux_ou_montant, imposable)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        primes
    )

    # ══════════════════════════════════════════════════════════════════
    # 7. TYPES D'ÉLÉMENTS VARIABLES
    # ══════════════════════════════════════════════════════════════════
    types_evs = [
        ('HS_25',      'Heures supplémentaires 25%',      'gain',    'horaire',    1, None),
        ('HS_50',      'Heures supplémentaires 50%',      'gain',    'horaire',    1, None),
        ('MISSION_I',  'Indemnité de mission intérieure',  'gain',    'journalier', 0, None),
        ('MISSION_E',  'Indemnité de mission extérieure',  'gain',    'journalier', 0, None),
        ('PRIME_REND', 'Prime de rendement',               'gain',    'fixe',       1, 200000),
        ('ABS_INJ',    'Retenue absence injustifiée',      'retenue', 'journalier', 0, None),
        ('PRET_IPRES', 'Remboursement prêt IPRES',        'retenue', 'fixe',       0, None),
        ('PRET_BANQ',  'Retenue bancaire',                 'retenue', 'fixe',       0, None),
    ]
    cur.executemany(
        """INSERT INTO types_evs
           (code, libelle, type_evs, mode_calcul, imposable, plafond)
           VALUES (?, ?, ?, ?, ?, ?)""",
        types_evs
    )

    # ══════════════════════════════════════════════════════════════════
    # 8. PARAMÈTRES DE PAIE — Valeur du point 2026
    # ══════════════════════════════════════════════════════════════════
    for month in range(1, 13):
        cur.execute(
            "INSERT INTO parametres_paie (code, libelle, valeur, periode) VALUES (?, ?, ?, ?)",
            ('VALEUR_POINT', 'Valeur du point d\'indice', 475.0, f'2026-{month:02d}')
        )

    # ══════════════════════════════════════════════════════════════════
    # 9. UTILISATEURS
    # ══════════════════════════════════════════════════════════════════
    utilisateurs = [
        ('admin',    hash_password('admin123'), 'Administrateur Système',  'admin',        None),
        ('rh_mfin',  hash_password('rh123'),    'Gestionnaire RH Finances','gestionnaire', 1),
        ('rh_msant', hash_password('rh123'),    'Gestionnaire RH Santé',   'gestionnaire', 2),
        ('rh_meduc', hash_password('rh123'),    'Gestionnaire RH Éducation','gestionnaire',3),
        ('rh_farme', hash_password('rh123'),    'Gestionnaire RH Forces Armées','gestionnaire',5),
    ]
    cur.executemany(
        "INSERT INTO utilisateurs (login, mot_de_passe_hash, nom, role, ministere_id) VALUES (?, ?, ?, ?, ?)",
        utilisateurs
    )

    # ══════════════════════════════════════════════════════════════════
    # 10. AGENTS (50) — Seed fixe pour reproductibilité
    # ══════════════════════════════════════════════════════════════════
    random.seed(42)

    noms_m = [
        'Diop', 'Ndiaye', 'Fall', 'Seck', 'Ba', 'Sy', 'Mbaye', 'Gueye',
        'Sarr', 'Diallo', 'Touré', 'Kane', 'Cissé', 'Diouf', 'Thiam',
        'Sow', 'Ndoye', 'Faye', 'Ly', 'Mbow', 'Camara', 'Sané', 'Tall',
        'Dieng', 'Niang', 'Bâ', 'Dème', 'Samb', 'Guèye', 'Mbengue',
    ]
    prenoms_m = [
        'Mamadou', 'Ibrahima', 'Ousmane', 'Moussa', 'Abdoulaye', 'Cheikh',
        'Modou', 'Pape', 'Aliou', 'Seydou', 'Babacar', 'Amadou', 'Lamine',
        'Omar', 'Bassirou', 'El Hadji', 'Djibril', 'Malick', 'Assane', 'Daouda',
    ]
    prenoms_f = [
        'Fatou', 'Aminata', 'Aïssatou', 'Mariama', 'Khady', 'Ndèye',
        'Awa', 'Coumba', 'Rama', 'Sokhna', 'Adja', 'Daba', 'Mame',
        'Seynabou', 'Rokhaya', 'Bineta', 'Yacine', 'Astou', 'Diary', 'Ngoné',
    ]

    situations = ['Célibataire', 'Marié(e)', 'Marié(e)', 'Divorcé(e)', 'Veuf(ve)']

    # Configuration des profils par statut
    profils_titulaire = [
        ('Administrateur Civil', 'Grade A1', [1,2,3], [300,330,360]),
        ('Administrateur Civil', 'Grade A2', [1,2,3], [400,440,480]),
        ('Médecin',              'Grade A1', [1,2,3], [450,490,530]),
        ('Médecin',              'Grade A2', [1,2],   [550,600]),
        ('Instituteur',          'Grade B1', [1,2,3], [200,220,240]),
        ('Instituteur',          'Grade B2', [1,2,3], [250,275,300]),
        ('Agent Administratif',  'Grade C1', [1,2,3], [150,165,180]),
        ('Agent Administratif',  'Grade C2', [1,2],   [180,200]),
    ]
    profils_contractuel = [
        ('Contractuel', 'Catégorie I',   [1,2], [350,380]),
        ('Contractuel', 'Catégorie II',  [1,2], [280,310]),
        ('Contractuel', 'Catégorie III', [1,2], [200,220]),
    ]
    profils_militaire = [
        ('Officier',      'Colonel',    [1], [600]),
        ('Officier',      'Capitaine',  [1,2], [400,430]),
        ('Officier',      'Lieutenant', [1,2], [340,360]),
        ('Sous-Officier', 'Adjudant',   [1,2], [250,270]),
        ('Sous-Officier', 'Sergent',    [1,2], [200,215]),
    ]
    profils_gendarmerie = [
        ('Officier',      'Colonel',   [1], [620]),
        ('Officier',      'Capitaine', [1,2], [410,440]),
        ('Sous-Officier', 'Adjudant',  [1,2], [260,280]),
        ('Sous-Officier', 'Gendarme',  [1,2], [180,195]),
    ]
    profils_police = [
        ('Officier',      'Commissaire',       [1,2], [430,460]),
        ('Officier',      'Inspecteur',        [1,2], [320,345]),
        ('Sous-Officier', 'Brigadier',         [1,2], [220,240]),
        ('Sous-Officier', 'Gardien de la Paix',[1,2], [180,195]),
    ]

    # Services par ministère
    services_par_ministere = {
        1: [1, 2, 3],    # Finances
        2: [4, 5],        # Santé
        3: [6, 7],        # Éducation
        4: [8],           # Justice
        5: [9, 10],       # Forces Armées
    }

    agents_data = []
    for i in range(1, 51):
        matricule = f'SN{10000 + i:06d}'
        sexe = random.choice(['M', 'F'])
        nom = random.choice(noms_m)
        prenom = random.choice(prenoms_m if sexe == 'M' else prenoms_f)
        annee_naiss = random.randint(1965, 2000)
        mois_naiss = random.randint(1, 12)
        jour_naiss = random.randint(1, 28)
        date_naissance = f'{annee_naiss}-{mois_naiss:02d}-{jour_naiss:02d}'
        situation = random.choice(situations)
        nb_enfants = random.randint(0, 5) if situation == 'Marié(e)' else random.randint(0, 2)

        annee_entree = random.randint(2005, 2024)
        date_entree = f'{annee_entree}-{random.randint(1,12):02d}-01'

        # Répartition : 60% titulaires, 20% contractuels, 20% forces
        if i <= 30:
            statut = 'titulaire'
            profil = random.choice(profils_titulaire)
            ministere_id = random.choice([1, 2, 3, 4])
        elif i <= 40:
            statut = 'contractuel'
            profil = random.choice(profils_contractuel)
            ministere_id = random.choice([1, 2, 3, 4])
        elif i <= 44:
            statut = 'militaire'
            profil = random.choice(profils_militaire)
            ministere_id = 5
        elif i <= 47:
            statut = 'gendarmerie'
            profil = random.choice(profils_gendarmerie)
            ministere_id = 5
        else:
            statut = 'police'
            profil = random.choice(profils_police)
            ministere_id = random.choice([1, 4])  # Police dans Finances ou Justice

        corps, grade = profil[0], profil[1]
        ech_idx = random.randint(0, len(profil[2]) - 1)
        echelon = profil[2][ech_idx]
        indice = profil[3][ech_idx]

        service_id = random.choice(services_par_ministere[ministere_id])

        agents_data.append((
            matricule, nom, prenom, date_naissance, sexe, statut,
            corps, grade, echelon, indice, situation, nb_enfants,
            service_id, date_entree
        ))

    cur.executemany(
        """INSERT INTO agents
           (matricule, nom, prenom, date_naissance, sexe, statut,
            corps, grade, echelon, indice, situation_matrimoniale, nb_enfants,
            service_id, date_entree)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        agents_data
    )

    # ══════════════════════════════════════════════════════════════════
    # 11. ÉLÉMENTS VARIABLES DE DÉMO (15 entrées pour mars 2026)
    # ══════════════════════════════════════════════════════════════════
    evs_demo = [
        (1,  1, '2026-03', 10, 0,    'valide',     'admin', 'Heures sup validées'),
        (3,  2, '2026-03', 5,  0,    'valide',     'admin', 'HS50 validées'),
        (5,  3, '2026-03', 3,  0,    'visa',       'admin', 'Mission Tambacounda'),
        (7,  4, '2026-03', 5,  0,    'en_attente',  None,   None),
        (10, 5, '2026-03', 0,  150000,'valide',    'admin', 'Prime rendement Q1'),
        (12, 1, '2026-03', 8,  0,    'en_attente',  None,   None),
        (15, 6, '2026-03', 2,  0,    'rejete',     'admin', 'Absence non justifiée confirmée'),
        (2,  7, '2026-03', 0,  45000,'visa',       'admin', 'Prêt IPRES mensuel'),
        (8,  8, '2026-03', 0,  30000,'valide',     'admin', 'Retenue bancaire'),
        (20, 1, '2026-03', 15, 0,    'en_attente',  None,   None),
        (25, 3, '2026-03', 4,  0,    'valide',     'admin', 'Mission intérieure validée'),
        (30, 5, '2026-03', 0,  180000,'en_attente', None,   'Prime rendement en attente'),
        (35, 2, '2026-03', 6,  0,    'visa',       'admin', 'HS50 visées par contrôleur'),
        (40, 4, '2026-03', 7,  0,    'en_attente',  None,   None),
        (45, 6, '2026-03', 1,  0,    'valide',     'admin', '1 jour absence retenu'),
    ]
    cur.executemany(
        """INSERT INTO elements_variables
           (agent_id, type_evs_id, periode, quantite, montant, statut_validation, validateur, commentaire)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        evs_demo
    )

    conn.commit()
    print("✅ Données de démonstration insérées (50 agents, 5 ministères, 15 EVS)")


if __name__ == '__main__':
    init_db()

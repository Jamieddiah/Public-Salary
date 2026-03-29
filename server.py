#!/usr/bin/env python3
"""
SIRH — Serveur HTTP
Administration Publique Sénégalaise

Lancement : python3 server.py → http://localhost:8080
"""

import http.server
import json
import hashlib
import uuid
import sqlite3
import os
import sys
import urllib.parse
from datetime import datetime

# Ajouter le répertoire racine au path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

DB_PATH = os.path.join(ROOT_DIR, 'sirh.db')
STATIC_DIR = os.path.join(ROOT_DIR, 'static')
EXPORTS_DIR = os.path.join(ROOT_DIR, 'exports')

# Sessions en mémoire {token: user_dict}
SESSIONS = {}


# ══════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def audit_log(user_id, action, table_cible=None, enregistrement_id=None, details=None):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO journal_audit (utilisateur_id, action, table_cible, enregistrement_id, details) VALUES (?, ?, ?, ?, ?)",
            (user_id, action, table_cible, enregistrement_id, details)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
# HANDLER HTTP
# ══════════════════════════════════════════════════════════════════════

class SIRHHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    # ── Suppression des logs verbeux ────────────────────────────────
    def log_message(self, format, *args):
        if '/api/' in str(args[0]) if args else False:
            print(f"  API  {args[0]}")

    # ── CORS ────────────────────────────────────────────────────────
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    # ── Helpers réponse ─────────────────────────────────────────────
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json({'error': message}, status)

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def get_current_user(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
            return SESSIONS.get(token)
        return None

    def get_query_params(self):
        parsed = urllib.parse.urlparse(self.path)
        return dict(urllib.parse.parse_qsl(parsed.query))

    def get_path(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path

    # ── Routage GET ─────────────────────────────────────────────────
    def do_GET(self):
        path = self.get_path()

        if path.startswith('/api/'):
            self.route_api('GET', path)
        elif path.startswith('/exports/'):
            # Servir les fichiers PDF
            file_path = os.path.join(ROOT_DIR, path.lstrip('/'))
            if os.path.exists(file_path):
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
                self.send_cors_headers()
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error_json(404, 'Fichier non trouvé')
        else:
            # SPA : servir index.html pour toutes les routes non-API
            if path == '/' or not os.path.exists(os.path.join(STATIC_DIR, path.lstrip('/'))):
                self.path = '/index.html'
            super().do_GET()

    def do_POST(self):
        path = self.get_path()
        if path.startswith('/api/'):
            self.route_api('POST', path)
        else:
            self.send_error_json(404, 'Route non trouvée')

    def do_PUT(self):
        path = self.get_path()
        if path.startswith('/api/'):
            self.route_api('PUT', path)
        else:
            self.send_error_json(404, 'Route non trouvée')

    # ── Routeur API ─────────────────────────────────────────────────
    def route_api(self, method, path):
        try:
            # Auth (pas besoin de token)
            if path == '/api/auth/login' and method == 'POST':
                return self.api_login()

            # Vérifier l'authentification pour toutes les autres routes
            user = self.get_current_user()
            if not user:
                return self.send_error_json(401, 'Non authentifié')

            # Stats
            if path == '/api/stats' and method == 'GET':
                return self.api_stats(user)

            # Organisation
            if path == '/api/organigramme' and method == 'GET':
                return self.api_organigramme(user)
            if path == '/api/services' and method == 'GET':
                return self.api_services(user)

            # Agents
            if path == '/api/agents' and method == 'GET':
                return self.api_agents_list(user)
            if path == '/api/agents' and method == 'POST':
                return self.api_agents_create(user)
            if path.startswith('/api/agents/') and method == 'GET':
                agent_id = int(path.split('/')[-1])
                return self.api_agents_detail(user, agent_id)
            if path.startswith('/api/agents/') and method == 'PUT':
                agent_id = int(path.split('/')[-1])
                return self.api_agents_update(user, agent_id)

            # Grilles et paramètres
            if path == '/api/grilles' and method == 'GET':
                return self.api_grilles(user)
            if path == '/api/parametres' and method == 'GET':
                return self.api_parametres(user)
            if path == '/api/parametres/valeur-point' and method == 'POST':
                return self.api_update_valeur_point(user)

            # EVS
            if path == '/api/evs' and method == 'GET':
                return self.api_evs_list(user)
            if path == '/api/evs/types' and method == 'GET':
                return self.api_evs_types(user)
            if path == '/api/evs' and method == 'POST':
                return self.api_evs_create(user)
            if path.endswith('/valider') and '/api/evs/' in path and method == 'POST':
                evs_id = int(path.split('/')[-2])
                return self.api_evs_valider(user, evs_id)

            # Paie
            if path == '/api/bulletins/calculer' and method == 'POST':
                return self.api_calculer_bulletin(user)
            if path == '/api/bulletins/batch' and method == 'POST':
                return self.api_calculer_batch(user)
            if path.endswith('/pdf') and '/api/bulletins/' in path and method == 'GET':
                bulletin_id = int(path.split('/')[-2])
                return self.api_bulletin_pdf(user, bulletin_id)

            # Rapport
            if path == '/api/rapport/masse-salariale' and method == 'GET':
                return self.api_rapport_masse_salariale(user)

            self.send_error_json(404, f'Route non trouvée: {method} {path}')

        except ValueError as e:
            self.send_error_json(400, str(e))
        except Exception as e:
            print(f"  ❌ Erreur API: {e}")
            import traceback
            traceback.print_exc()
            self.send_error_json(500, f'Erreur serveur: {str(e)}')

    # ════════════════════════════════════════════════════════════════
    # AUTHENTIFICATION
    # ════════════════════════════════════════════════════════════════

    def api_login(self):
        body = self.read_body()
        login = body.get('login', '')
        mot_de_passe = body.get('mot_de_passe', '')

        if not login or not mot_de_passe:
            return self.send_error_json(400, 'Login et mot de passe requis')

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM utilisateurs WHERE login = ? AND actif = 1",
            (login,)
        ).fetchone()
        conn.close()

        if not user or user['mot_de_passe_hash'] != hash_password(mot_de_passe):
            return self.send_error_json(401, 'Identifiants incorrects')

        token = str(uuid.uuid4())
        user_data = {
            'id': user['id'],
            'login': user['login'],
            'nom': user['nom'],
            'role': user['role'],
            'ministere_id': user['ministere_id'],
        }
        SESSIONS[token] = user_data

        audit_log(user['id'], 'LOGIN', 'utilisateurs', user['id'])
        self.send_json({'token': token, 'user': user_data})

    # ════════════════════════════════════════════════════════════════
    # STATS (Dashboard)
    # ════════════════════════════════════════════════════════════════

    def api_stats(self, user):
        conn = get_db()

        total = conn.execute("SELECT COUNT(*) as c FROM agents WHERE actif=1").fetchone()['c']

        par_statut = {}
        for row in conn.execute("SELECT statut, COUNT(*) as c FROM agents WHERE actif=1 GROUP BY statut"):
            par_statut[row['statut']] = row['c']

        total_min = conn.execute("SELECT COUNT(*) as c FROM ministeres WHERE actif=1").fetchone()['c']
        evs_attente = conn.execute("SELECT COUNT(*) as c FROM elements_variables WHERE statut_validation='en_attente'").fetchone()['c']

        derniers = conn.execute("""
            SELECT a.id, a.matricule, a.nom, a.prenom, a.statut, a.corps, a.grade, a.date_entree,
                   m.nom as ministere_nom
            FROM agents a
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN directions d ON s.direction_id = d.id
            LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
            LEFT JOIN ministeres m ON dg.ministere_id = m.id
            WHERE a.actif = 1
            ORDER BY a.id DESC LIMIT 5
        """).fetchall()

        conn.close()

        self.send_json({
            'total_agents': total,
            'agents_par_statut': par_statut,
            'total_ministeres': total_min,
            'evs_en_attente': evs_attente,
            'derniers_agents': [dict(r) for r in derniers],
        })

    # ════════════════════════════════════════════════════════════════
    # ORGANISATION
    # ════════════════════════════════════════════════════════════════

    def api_organigramme(self, user):
        conn = get_db()
        ministeres = conn.execute("SELECT * FROM ministeres WHERE actif=1 ORDER BY nom").fetchall()
        result = []

        for m in ministeres:
            dgs = conn.execute(
                "SELECT * FROM directions_generales WHERE ministere_id=? AND actif=1 ORDER BY nom",
                (m['id'],)
            ).fetchall()

            dgs_list = []
            for dg in dgs:
                dirs = conn.execute(
                    "SELECT * FROM directions WHERE direction_generale_id=? AND actif=1 ORDER BY nom",
                    (dg['id'],)
                ).fetchall()

                dirs_list = []
                for d in dirs:
                    svcs = conn.execute("""
                        SELECT s.*, COUNT(a.id) as nb_agents
                        FROM services s
                        LEFT JOIN agents a ON a.service_id = s.id AND a.actif = 1
                        WHERE s.direction_id = ? AND s.actif = 1
                        GROUP BY s.id
                        ORDER BY s.nom
                    """, (d['id'],)).fetchall()

                    dirs_list.append({
                        **dict(d),
                        'services': [dict(s) for s in svcs],
                    })

                dgs_list.append({
                    **dict(dg),
                    'directions': dirs_list,
                })

            result.append({
                **dict(m),
                'directions_generales': dgs_list,
            })

        conn.close()
        self.send_json(result)

    def api_services(self, user):
        conn = get_db()
        rows = conn.execute("""
            SELECT s.id, s.code, s.nom, s.chef_service,
                   d.nom as direction_nom,
                   dg.nom as dg_nom,
                   m.nom as ministere_nom, m.id as ministere_id
            FROM services s
            JOIN directions d ON s.direction_id = d.id
            JOIN directions_generales dg ON d.direction_generale_id = dg.id
            JOIN ministeres m ON dg.ministere_id = m.id
            WHERE s.actif = 1
            ORDER BY m.nom, dg.nom, d.nom, s.nom
        """).fetchall()
        conn.close()
        self.send_json([dict(r) for r in rows])

    # ════════════════════════════════════════════════════════════════
    # AGENTS
    # ════════════════════════════════════════════════════════════════

    def _get_agent_ministere_id(self, conn, agent_id):
        """Récupérer le ministere_id d'un agent."""
        row = conn.execute("""
            SELECT m.id
            FROM agents a
            JOIN services s ON a.service_id = s.id
            JOIN directions d ON s.direction_id = d.id
            JOIN directions_generales dg ON d.direction_generale_id = dg.id
            JOIN ministeres m ON dg.ministere_id = m.id
            WHERE a.id = ?
        """, (agent_id,)).fetchone()
        return row['id'] if row else None

    def api_agents_list(self, user):
        params = self.get_query_params()
        conn = get_db()

        where = ["a.actif = 1"]
        args = []

        # Filtrage gestionnaire par ministère
        if user['role'] == 'gestionnaire' and user.get('ministere_id'):
            where.append("m.id = ?")
            args.append(user['ministere_id'])

        if params.get('statut'):
            where.append("a.statut = ?")
            args.append(params['statut'])

        if params.get('ministere_id'):
            where.append("m.id = ?")
            args.append(int(params['ministere_id']))

        if params.get('service_id'):
            where.append("a.service_id = ?")
            args.append(int(params['service_id']))

        if params.get('q'):
            q = f"%{params['q']}%"
            where.append("(a.nom LIKE ? OR a.prenom LIKE ? OR a.matricule LIKE ?)")
            args.extend([q, q, q])

        where_clause = " AND ".join(where)

        # Comptage total
        count_sql = f"""
            SELECT COUNT(*) as c FROM agents a
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN directions d ON s.direction_id = d.id
            LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
            LEFT JOIN ministeres m ON dg.ministere_id = m.id
            WHERE {where_clause}
        """
        total = conn.execute(count_sql, args).fetchone()['c']

        page = int(params.get('page', 1))
        per_page = int(params.get('per_page', 20))
        offset = (page - 1) * per_page

        sql = f"""
            SELECT a.*, s.nom as service_nom,
                   d.nom as direction_nom,
                   dg.nom as dg_nom,
                   m.nom as ministere_nom, m.id as ministere_id
            FROM agents a
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN directions d ON s.direction_id = d.id
            LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
            LEFT JOIN ministeres m ON dg.ministere_id = m.id
            WHERE {where_clause}
            ORDER BY a.nom, a.prenom
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(sql, args + [per_page, offset]).fetchall()
        conn.close()

        self.send_json({
            'agents': [dict(r) for r in rows],
            'total': total,
            'page': page,
            'per_page': per_page,
        })

    def api_agents_detail(self, user, agent_id):
        conn = get_db()

        # Vérifier accès gestionnaire
        if user['role'] == 'gestionnaire' and user.get('ministere_id'):
            mid = self._get_agent_ministere_id(conn, agent_id)
            if mid != user['ministere_id']:
                conn.close()
                return self.send_error_json(403, 'Accès interdit')

        agent = conn.execute("""
            SELECT a.*, s.nom as service_nom,
                   d.nom as direction_nom,
                   dg.nom as dg_nom,
                   m.nom as ministere_nom, m.id as ministere_id
            FROM agents a
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN directions d ON s.direction_id = d.id
            LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
            LEFT JOIN ministeres m ON dg.ministere_id = m.id
            WHERE a.id = ?
        """, (agent_id,)).fetchone()

        if not agent:
            conn.close()
            return self.send_error_json(404, 'Agent non trouvé')

        bulletins = conn.execute(
            "SELECT * FROM bulletins WHERE agent_id = ? ORDER BY periode DESC LIMIT 6",
            (agent_id,)
        ).fetchall()

        evs = conn.execute("""
            SELECT ev.*, te.code as type_code, te.libelle as type_libelle, te.type_evs
            FROM elements_variables ev
            JOIN types_evs te ON ev.type_evs_id = te.id
            WHERE ev.agent_id = ?
            ORDER BY ev.periode DESC, ev.id DESC
            LIMIT 10
        """, (agent_id,)).fetchall()

        conn.close()

        self.send_json({
            'agent': dict(agent),
            'bulletins': [dict(b) for b in bulletins],
            'evs': [dict(e) for e in evs],
        })

    def api_agents_create(self, user):
        if user['role'] in ('controleur', 'auditeur'):
            return self.send_error_json(403, 'Permission insuffisante')

        body = self.read_body()
        conn = get_db()

        # Auto-générer le matricule
        matricule = body.get('matricule')
        if not matricule:
            last = conn.execute("SELECT matricule FROM agents ORDER BY id DESC LIMIT 1").fetchone()
            if last:
                num = int(last['matricule'][2:]) + 1
            else:
                num = 10001
            matricule = f'SN{num:06d}'

        try:
            conn.execute("""
                INSERT INTO agents (matricule, nom, prenom, date_naissance, sexe, statut,
                    corps, grade, echelon, indice, situation_matrimoniale, nb_enfants,
                    service_id, date_entree)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                matricule, body.get('nom', ''), body.get('prenom', ''),
                body.get('date_naissance'), body.get('sexe', 'M'),
                body.get('statut', 'titulaire'), body.get('corps', ''),
                body.get('grade', ''), int(body.get('echelon', 1)),
                int(body.get('indice', 0)),
                body.get('situation_matrimoniale', 'Célibataire'),
                int(body.get('nb_enfants', 0)),
                int(body.get('service_id', 1)) if body.get('service_id') else 1,
                body.get('date_entree', datetime.now().strftime('%Y-%m-%d'))
            ))
            conn.commit()
            agent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()

            audit_log(user['id'], 'CREATE', 'agents', agent_id, f'Matricule: {matricule}')
            self.send_json({'id': agent_id, 'matricule': matricule, 'message': 'Agent créé'}, 201)
        except Exception as e:
            conn.close()
            self.send_error_json(400, str(e))

    def api_agents_update(self, user, agent_id):
        if user['role'] in ('controleur', 'auditeur'):
            return self.send_error_json(403, 'Permission insuffisante')

        body = self.read_body()
        conn = get_db()

        fields = []
        values = []
        allowed = ['nom', 'prenom', 'date_naissance', 'sexe', 'statut', 'corps', 'grade',
                    'echelon', 'indice', 'situation_matrimoniale', 'nb_enfants', 'service_id', 'actif']

        for field in allowed:
            if field in body:
                fields.append(f"{field} = ?")
                values.append(body[field])

        if not fields:
            conn.close()
            return self.send_error_json(400, 'Aucun champ à modifier')

        values.append(agent_id)
        conn.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()

        audit_log(user['id'], 'UPDATE', 'agents', agent_id, json.dumps(body, ensure_ascii=False))
        self.send_json({'message': 'Agent modifié'})

    # ════════════════════════════════════════════════════════════════
    # GRILLES ET PARAMÈTRES
    # ════════════════════════════════════════════════════════════════

    def api_grilles(self, user):
        params = self.get_query_params()
        conn = get_db()

        where = []
        args = []

        if params.get('statut'):
            where.append("statut = ?")
            args.append(params['statut'])
        if params.get('corps'):
            where.append("corps = ?")
            args.append(params['corps'])

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = conn.execute(
            f"SELECT * FROM grilles_indiciaires {where_clause} ORDER BY statut, corps, grade, echelon",
            args
        ).fetchall()
        conn.close()

        # Ajouter le salaire de base calculé
        result = []
        for r in rows:
            d = dict(r)
            d['salaire_base'] = r['indice'] * 475  # Valeur par défaut
            result.append(d)

        self.send_json(result)

    def api_parametres(self, user):
        conn = get_db()
        rows = conn.execute("SELECT * FROM parametres_paie ORDER BY periode DESC, code").fetchall()
        conn.close()
        self.send_json([dict(r) for r in rows])

    def api_update_valeur_point(self, user):
        if user['role'] != 'admin':
            return self.send_error_json(403, 'Admin uniquement')

        body = self.read_body()
        periode = body.get('periode')
        valeur = body.get('valeur')

        if not periode or not valeur:
            return self.send_error_json(400, 'Période et valeur requises')

        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM parametres_paie WHERE code='VALEUR_POINT' AND periode=?",
            (periode,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE parametres_paie SET valeur=? WHERE id=?",
                (float(valeur), existing['id'])
            )
        else:
            conn.execute(
                "INSERT INTO parametres_paie (code, libelle, valeur, periode) VALUES (?, ?, ?, ?)",
                ('VALEUR_POINT', "Valeur du point d'indice", float(valeur), periode)
            )

        conn.commit()
        conn.close()

        audit_log(user['id'], 'UPDATE_VALEUR_POINT', 'parametres_paie', None, f'{periode}: {valeur}')
        self.send_json({'message': f'Valeur du point mise à jour pour {periode}'})

    # ════════════════════════════════════════════════════════════════
    # ÉLÉMENTS VARIABLES
    # ════════════════════════════════════════════════════════════════

    def api_evs_list(self, user):
        params = self.get_query_params()
        conn = get_db()

        where = []
        args = []

        if params.get('statut_validation'):
            where.append("ev.statut_validation = ?")
            args.append(params['statut_validation'])
        if params.get('periode'):
            where.append("ev.periode = ?")
            args.append(params['periode'])
        if params.get('agent_id'):
            where.append("ev.agent_id = ?")
            args.append(int(params['agent_id']))

        # Filtrage gestionnaire par ministère
        if user['role'] == 'gestionnaire' and user.get('ministere_id'):
            where.append("m.id = ?")
            args.append(user['ministere_id'])

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""

        rows = conn.execute(f"""
            SELECT ev.*, te.code as type_code, te.libelle as type_libelle, te.type_evs,
                   a.matricule, a.nom as agent_nom, a.prenom as agent_prenom, a.statut as agent_statut,
                   m.id as ministere_id
            FROM elements_variables ev
            JOIN types_evs te ON ev.type_evs_id = te.id
            JOIN agents a ON ev.agent_id = a.id
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN directions d ON s.direction_id = d.id
            LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
            LEFT JOIN ministeres m ON dg.ministere_id = m.id
            {where_clause}
            ORDER BY ev.date_creation DESC
        """, args).fetchall()
        conn.close()

        self.send_json([dict(r) for r in rows])

    def api_evs_types(self, user):
        conn = get_db()
        rows = conn.execute("SELECT * FROM types_evs ORDER BY type_evs, code").fetchall()
        conn.close()
        self.send_json([dict(r) for r in rows])

    def api_evs_create(self, user):
        if user['role'] == 'auditeur':
            return self.send_error_json(403, 'Permission insuffisante')

        body = self.read_body()
        conn = get_db()

        try:
            conn.execute("""
                INSERT INTO elements_variables (agent_id, type_evs_id, periode, quantite, montant, statut_validation)
                VALUES (?, ?, ?, ?, ?, 'en_attente')
            """, (
                int(body['agent_id']),
                int(body['type_evs_id']),
                body['periode'],
                float(body.get('quantite', 0)),
                float(body.get('montant', 0)),
            ))
            conn.commit()
            evs_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()

            audit_log(user['id'], 'CREATE', 'elements_variables', evs_id)
            self.send_json({'id': evs_id, 'message': 'EVS créé'}, 201)
        except Exception as e:
            conn.close()
            self.send_error_json(400, str(e))

    def api_evs_valider(self, user, evs_id):
        body = self.read_body()
        action = body.get('action')  # valider, rejeter, visa

        if action not in ('valider', 'rejeter', 'visa'):
            return self.send_error_json(400, 'Action invalide (valider, rejeter, visa)')

        # Vérifier les permissions
        if user['role'] == 'auditeur':
            return self.send_error_json(403, 'Permission insuffisante')
        if action == 'visa' and user['role'] not in ('admin', 'controleur'):
            return self.send_error_json(403, 'Seul admin/contrôleur peut viser')

        statut_map = {'valider': 'valide', 'rejeter': 'rejete', 'visa': 'visa'}

        conn = get_db()
        conn.execute(
            "UPDATE elements_variables SET statut_validation=?, validateur=?, commentaire=? WHERE id=?",
            (statut_map[action], user['login'], body.get('commentaire', ''), evs_id)
        )
        conn.commit()
        conn.close()

        audit_log(user['id'], f'EVS_{action.upper()}', 'elements_variables', evs_id)
        self.send_json({'message': f'EVS {statut_map[action]}'})

    # ════════════════════════════════════════════════════════════════
    # PAIE
    # ════════════════════════════════════════════════════════════════

    def api_calculer_bulletin(self, user):
        if user['role'] == 'auditeur':
            return self.send_error_json(403, 'Permission insuffisante')

        body = self.read_body()
        agent_id = body.get('agent_id')
        periode = body.get('periode', '2026-03')

        if not agent_id:
            return self.send_error_json(400, 'agent_id requis')

        from database.moteur_paie import calculer_bulletin
        result = calculer_bulletin(DB_PATH, int(agent_id), periode)

        if 'error' in result:
            return self.send_error_json(400, result['error'])

        audit_log(user['id'], 'CALCULER_BULLETIN', 'bulletins', result.get('bulletin_id'), f'Agent {agent_id}, période {periode}')
        self.send_json(result)

    def api_calculer_batch(self, user):
        if user['role'] != 'admin':
            return self.send_error_json(403, 'Admin uniquement')

        body = self.read_body()
        periode = body.get('periode', '2026-03')

        from database.moteur_paie import calculer_batch
        result = calculer_batch(DB_PATH, periode)

        audit_log(user['id'], 'CALCULER_BATCH', 'bulletins', None, f'Période {periode}, {result["total_calcules"]} bulletins')
        self.send_json(result)

    def api_bulletin_pdf(self, user, bulletin_id):
        conn = get_db()
        bulletin = conn.execute("SELECT * FROM bulletins WHERE id = ?", (bulletin_id,)).fetchone()
        if not bulletin:
            conn.close()
            return self.send_error_json(404, 'Bulletin non trouvé')

        agent = conn.execute("""
            SELECT a.*, s.nom as service_nom, d.nom as direction_nom,
                   dg.nom as dg_nom, m.nom as ministere_nom
            FROM agents a
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN directions d ON s.direction_id = d.id
            LEFT JOIN directions_generales dg ON d.direction_generale_id = dg.id
            LEFT JOIN ministeres m ON dg.ministere_id = m.id
            WHERE a.id = ?
        """, (bulletin['agent_id'],)).fetchone()

        lignes = conn.execute(
            "SELECT * FROM lignes_bulletin WHERE bulletin_id = ? ORDER BY id",
            (bulletin_id,)
        ).fetchall()
        conn.close()

        # Générer le PDF
        try:
            from database.pdf_generator import generer_bulletin_pdf
            filepath = generer_bulletin_pdf(dict(bulletin), dict(agent), [dict(l) for l in lignes])
            # Retourner le chemin du fichier
            filename = os.path.basename(filepath)
            self.send_json({'pdf_url': f'/exports/{filename}', 'message': 'PDF généré'})
        except ImportError:
            self.send_error_json(500, 'Module PDF non disponible. Installez reportlab: pip3 install reportlab')
        except Exception as e:
            self.send_error_json(500, f'Erreur génération PDF: {str(e)}')

    def api_rapport_masse_salariale(self, user):
        params = self.get_query_params()
        periode = params.get('periode', '2026-03')
        niveau = params.get('niveau', 'ministere')

        from database.moteur_paie import rapport_masse_salariale
        result = rapport_masse_salariale(DB_PATH, periode, niveau)
        self.send_json(result)


# ══════════════════════════════════════════════════════════════════════
# LANCEMENT DU SERVEUR
# ══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # Initialiser la base de données
    from database.schema import init_db
    init_db(DB_PATH)

    # Créer le dossier exports
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    PORT = 8080
    server = http.server.HTTPServer(('', PORT), SIRHHandler)

    print()
    print("═" * 60)
    print("  🏛️  SIRH — Système d'Information des Ressources Humaines")
    print("  📍 Administration Publique Sénégalaise")
    print("═" * 60)
    print(f"  🌐 Serveur : http://localhost:{PORT}")
    print(f"  📁 Base    : {DB_PATH}")
    print(f"  📄 Static  : {STATIC_DIR}")
    print("─" * 60)
    print("  👤 Admin       : admin / admin123")
    print("  👤 RH Finances : rh_mfin / rh123")
    print("  👤 RH Santé    : rh_msant / rh123")
    print("  👤 RH Éducation: rh_meduc / rh123")
    print("  👤 RH Armées   : rh_farme / rh123")
    print("═" * 60)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Serveur arrêté.")
        server.server_close()

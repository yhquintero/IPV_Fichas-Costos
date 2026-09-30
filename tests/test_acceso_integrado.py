"""Acceso real: licencia, sesiones, roles y permisos se comprueban en cada petición."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import auth
import licencia
import rate_limiter
import server


class AccesoIntegradoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = (server.DB_PATH, server.REQUIRE_USERS, server.REQUIRE_LICENSE,
                   auth.JWT_SECRET, auth.JWT_ENABLED, server.LICENSE.pub,
                   server.LICENSE.dir, server.API_TOKEN)
        server.DB_PATH = Path(cls.tmp.name) / 'test.db'
        auth.JWT_SECRET, auth.JWT_ENABLED = 'acceso-integrado-' + 'x' * 40, True
        server.REQUIRE_USERS = server.REQUIRE_LICENSE = True
        server.init_db()
        with server.connect() as conn:
            for email, role in [('admin@test.cu', 'admin'), ('editor@test.cu', 'editor')]:
                auth.create_user(conn, {'email': email, 'name': email, 'role': role,
                                        'password': 'Clave-Segura#2026'}, server.now_iso)
        cls.store = server.LICENSE
        cls.d, cls.pub = licencia.generate_keypair()
        cls.store.pub, cls.store.dir, cls.store._cache = cls.pub, Path(cls.tmp.name), None
        server.API_TOKEN = 'token-solo-lectura-de-prueba'
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.httpd.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        (server.DB_PATH, server.REQUIRE_USERS, server.REQUIRE_LICENSE,
         auth.JWT_SECRET, auth.JWT_ENABLED, cls.store.pub, cls.store.dir,
         server.API_TOKEN) = cls.old
        cls.store._cache = None
        cls.tmp.cleanup()

    def setUp(self):
        rate_limiter._hits.clear()

    def req(self, method, path, body=None, token='', api_token=''):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if api_token:
            headers['X-API-Token'] = api_token
        request = urllib.request.Request(self.url + path, headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def login(self, email):
        return self.req('POST', '/api/auth/login',
                        {'email': email, 'password': 'Clave-Segura#2026'})

    def test_configuracion_inicial_solo_admin_y_sin_datos(self):
        original_pub = self.store.pub
        try:
            self.store.pub = ''
            status, info = self.req('GET', '/api/license')
            self.assertEqual(status, 200)
            self.assertTrue(info['setup_required'])
            self.assertFalse(info['valid'])
            self.assertEqual(self.req('GET', '/api/materials')[0], 401)  # primero JWT
            admin = self.login('admin@test.cu')[1]['access_token']
            editor = self.login('editor@test.cu')[1]['access_token']
            self.assertEqual(self.req('GET', '/api/materials', token=admin)[0], 402)
            self.assertEqual(self.req('GET', '/api/keygen/status', token=admin)[0], 200)
            self.assertEqual(self.req('GET', '/api/keygen/status', token=editor)[0], 403)
        finally:
            self.store.pub = original_pub

    def test_licencia_y_rol_en_cada_solicitud(self):
        self.assertEqual(self.login('admin@test.cu')[0], 402)
        self.assertEqual(self.req('GET', '/api/materials', api_token=server.API_TOKEN)[0], 402)
        lic = licencia.issue(self.d, 'Empresa', self.store.code, '1M')
        self.assertEqual(self.req('POST', '/api/license', {'license': lic})[0], 200)
        admin = self.login('admin@test.cu')[1]['access_token']
        editor = self.login('editor@test.cu')[1]['access_token']
        self.assertEqual(self.req('GET', '/api/keygen/status', token=editor)[0], 403)
        self.assertEqual(self.req('GET', '/api/keygen/status', api_token=server.API_TOKEN)[0], 401)
        self.assertEqual(self.req('GET', '/api/users', api_token=server.API_TOKEN)[0], 401)
        self.assertEqual(self.req('POST', '/api/products', {}, api_token=server.API_TOKEN)[0], 403)
        self.assertEqual(self.req('GET', '/api/materials', token=editor)[0], 200)
        # Licencia cambiada en disco: el resultado anterior NO se sirve desde la caché.
        (self.store.dir / 'licencia.lic').write_text('licencia-alterada')
        self.assertEqual(self.req('GET', '/api/materials', token=editor)[0], 402)
        self.assertEqual(self.req('GET', '/api/users', token=admin)[0], 402)
        self.assertEqual(self.req('GET', '/api/v1/materials', token=editor)[0], 402)
        self.assertEqual(self.req('POST', '/api/license', {'license': lic})[0], 200)
        self.assertEqual(self.req('GET', '/api/materials', token=editor)[0], 200)

    def test_recuperacion_administrativa_sin_abrir_datos(self):
        # Una instalación caducada no tiene sesión útil para emitir una licencia.
        (self.store.dir / 'licencia.lic').unlink(missing_ok=True)
        self.assertEqual(self.login('admin@test.cu')[0], 402)
        body = {'email': 'editor@test.cu', 'password': 'Clave-Segura#2026'}
        with server.connect() as conn:
            before = conn.execute("SELECT count(*) FROM sessions WHERE user_id=(SELECT id FROM users WHERE email='editor@test.cu')").fetchone()[0]
        self.assertEqual(self.req('POST', '/api/auth/maintenance-login', body)[0], 403)
        with server.connect() as conn:
            after = conn.execute("SELECT count(*) FROM sessions WHERE user_id=(SELECT id FROM users WHERE email='editor@test.cu')").fetchone()[0]
        self.assertEqual(after, before)  # denegación atómica: ningún JWT válido
        body['email'] = 'admin@test.cu'
        status, logged = self.req('POST', '/api/v1/auth/maintenance-login', body)
        self.assertEqual(status, 200, logged)
        token, refresh = logged['access_token'], logged['refresh_token']
        self.assertEqual(self.req('GET', '/api/materials', token=token)[0], 402)
        self.assertEqual(self.req('GET', '/api/keygen/status', token=token)[0], 200)
        self.assertEqual(self.req('POST', '/api/auth/refresh', {'refresh_token': refresh})[0], 402)
        status, refreshed = self.req('POST', '/api/auth/maintenance-refresh', {'refresh_token': refresh})
        self.assertEqual(status, 200, refreshed)
        self.assertEqual(self.req('GET', '/api/materials', token=refreshed['access_token'])[0], 402)

    def test_mfa_administrador_se_puede_configurar_sin_licencia(self):
        import enterprise
        import security
        old_mfa = enterprise.REQUIRE_ADMIN_MFA
        enterprise.REQUIRE_ADMIN_MFA = True
        (self.store.dir / 'licencia.lic').unlink(missing_ok=True)
        try:
            body = {'email': 'admin@test.cu', 'password': 'Clave-Segura#2026'}
            admin = self.req('POST', '/api/auth/maintenance-login', body)[1]['access_token']
            self.assertEqual(self.req('GET', '/api/keygen/status', token=admin)[0], 403)
            self.assertEqual(self.req('GET', '/api/auth/me', token=admin)[0], 200)
            status, setup = self.req('POST', '/api/auth/2fa/setup', {}, token=admin)
            self.assertEqual(status, 200, setup)
            code = security.totp_now(setup['secret'])
            status, enabled = self.req('POST', '/api/auth/2fa/enable', {'code': code}, token=admin)
            self.assertEqual(status, 200)
            self.assertEqual(self.req('GET', '/api/keygen/status', token=admin)[0], 401)
            st, missing = self.req('POST', '/api/auth/maintenance-login', body)
            self.assertEqual(st, 401)
            self.assertTrue(missing['mfa_required'])
            body['otp'] = enabled['recovery_codes'][0]
            status, new_session = self.req('POST', '/api/auth/maintenance-login', body)
            self.assertEqual(status, 200, new_session)
            self.assertEqual(self.req('GET', '/api/keygen/status', token=new_session['access_token'])[0], 200)
        finally:
            with server.connect() as conn:
                conn.execute("UPDATE users SET totp_enabled=0, totp_secret='', recovery_codes='', totp_last_step=-1 WHERE email='admin@test.cu'")
            enterprise.REQUIRE_ADMIN_MFA = old_mfa

    def test_stream_cierra_al_revocar_sesion_o_licencia(self):
        import enterprise
        lic = licencia.issue(self.d, 'Empresa', self.store.code, '1M')
        self.assertEqual(self.req('POST', '/api/license', {'license': lic})[0], 200)
        editor = self.login('editor@test.cu')[1]['access_token']
        request = urllib.request.Request(self.url + '/api/events',
                                         headers={'Authorization': 'Bearer ' + editor})
        with urllib.request.urlopen(request, timeout=3) as stream:
            self.assertEqual(stream.readline(), b'retry: 5000\n')
            self.assertEqual(stream.readline(), b'event: ready\n')
            stream.readline(); stream.readline()
            enterprise.bus.publish({'action': 'UPDATE_MATERIAL', 'details': 'precio-secreto', 'time': 'hoy'})
            self.assertEqual(stream.readline(), b'event: change\n')
            visible = json.loads(stream.readline().removeprefix(b'data: '))
            self.assertNotIn('details', visible)
            stream.readline()
            payload = auth.decode_token(editor)
            import permisos
            with server.connect() as conn:
                permisos.set_permissions(conn, payload['sub'], 'editor',
                    {'materials': {'view': False}}, server.now_iso)
            enterprise.bus.publish({'action': 'UPDATE_MATERIAL', 'details': 'oculto'})
            self.assertEqual(stream.readline(), b': ping\n')
            stream.readline()
            with server.connect() as conn:
                permisos.reset_permissions(conn, payload['sub'])
                auth.revoke_session(conn, payload['sub'], payload['sid'])
            enterprise.bus.publish({'action': 'UPDATE_MATERIAL', 'details': 'otro-precio'})
            self.assertEqual(stream.readline(), b'')
        # Otra conexión activa se cierra al perder la licencia.
        admin = self.login('admin@test.cu')[1]['access_token']
        with urllib.request.urlopen(urllib.request.Request(self.url + '/api/events',
                                    headers={'Authorization': 'Bearer ' + admin}), timeout=3) as stream:
            for _ in range(4): stream.readline()
            (self.store.dir / 'licencia.lic').unlink()
            enterprise.bus.publish({'action': 'UPDATE_MATERIAL', 'details': 'no-entregar'})
            self.assertEqual(stream.readline(), b'')

    def test_costos_y_fichas_no_se_filtran_solo_en_el_cliente(self):
        import permisos
        limited = permisos.defaults_for('editor')
        limited['fichas'] = {'view': True, 'edit': False, 'costs': False}
        user = {'permissions': limited}
        ficha = permisos.filter_response('/api/fichas/3',
            {'total_cost': '10', 'cost_per_serving': '5', 'items': [{'unit_cost': '5'}]}, user)
        self.assertIsNone(ficha['cost_per_serving'])
        self.assertIsNone(ficha['items'][0]['unit_cost'])
        product = permisos.filter_response('/api/products/1', {'fichas': [{'total_cost': '10'}]}, user)
        self.assertIsNone(product['fichas'][0]['total_cost'])
        control = permisos.filter_response('/api/controls/1',
            {'ficha_total': '10', 'cost_per_serving': '5'},
            {'permissions': {**limited, 'controls': {'view': True, 'edit': False, 'costs': False}}})
        self.assertIsNone(control['ficha_total'])
        limited['fichas']['view'] = False
        self.assertEqual(permisos.filter_response('/api/products/1', product, user)['fichas'], [])
        inv = permisos.filter_response('/api/inventory',
            {'items': [{'unit_price': '7', 'used_by': [{'ficha_id': 1}]}]}, user)
        self.assertEqual(inv['items'][0]['used_by'], [])

    def test_password_forzada_bloquea_token_ya_emitido(self):
        lic = licencia.issue(self.d, 'Empresa', self.store.code, '1M')
        self.req('POST', '/api/license', {'license': lic})
        editor = self.login('editor@test.cu')[1]['access_token']
        with server.connect() as conn:
            conn.execute("UPDATE users SET must_change_password=1 WHERE email='editor@test.cu'")
        status, body = self.req('GET', '/api/materials', token=editor)
        self.assertEqual(status, 403)
        self.assertTrue(body['password_expired'])
        with server.connect() as conn:
            conn.execute("UPDATE users SET must_change_password=0 WHERE email='editor@test.cu'")

    def test_arranque_sin_jwt_es_rechazado(self):
        import enterprise
        enabled, secret, backup_hours = auth.JWT_ENABLED, auth.JWT_SECRET, enterprise.BACKUP_INTERVAL_HOURS
        try:
            auth.JWT_ENABLED = False
            enterprise.BACKUP_INTERVAL_HOURS = 0
            with self.assertRaisesRegex(SystemExit, 'IPV_JWT_SECRET'):
                server.main()
            auth.JWT_ENABLED, auth.JWT_SECRET = True, 'corta'
            with self.assertRaisesRegex(SystemExit, '32 bytes'):
                server.main()
        finally:
            auth.JWT_ENABLED, auth.JWT_SECRET = enabled, secret
            enterprise.BACKUP_INTERVAL_HOURS = backup_hours

    def test_sesion_sin_sid_no_es_valida(self):
        with server.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email='editor@test.cu'").fetchone()
            payload = auth.decode_token(auth.encode_token(auth.public_user(row)), 'access')
            self.assertFalse(auth.session_valid(conn, payload))


if __name__ == '__main__':
    unittest.main()

"""Localisation (Turkish / English) and persistent user settings for smx.

On first run the language is detected from the environment (LC_ALL, LC_MESSAGES, LANG,
LANGUAGE) and stored in ~/.config/smx/settings.json together with other preferences.
"""
import json, os

LANGS = {'tr': 'Türkçe', 'en': 'English'}

S = {
    'tr': {
        'title': 'SMX-R22 Fare Kontrolü',
        'sec_dpi': 'DPI', 'sec_keys': 'Tuşlar', 'sec_led': 'Işık', 'sec_other': 'Diğer',
        'active_level': 'Aktif kademe', 'level': 'Kademe {n}', 'off': 'Kapalı',
        'mode': 'Mod', 'speed': 'Hız', 'brightness': 'Parlaklık',
        'fire': 'Hızlı ateş aralığı', 'language': 'Dil / Language', 'color_order': 'LED renk düzeni', 'inverted': 'ters',
        'factory_keys': 'Tuşları fabrika ayarına döndür', 'undo_all': 'Oturumdaki değişiklikleri geri al',
        'help_bar': '↑↓ seç   ←→ değiştir   Enter renk/liste   q çık',
        'h_active': 'Fare şu an bu kademede. Faredeki DPI tuşu da bunu değiştirir.',
        'h_level': '←→ DPI değeri ("Kapalı" = DPI tuşu atlar)   Enter: bu kademenin rengini değiştir',
        'h_key': '←→ temel işlev   Enter: kısayollar ve medya dahil tüm liste',
        'h_mode': '←→ ışık efekti, Enter: listeden seç.',
        'h_speed': 'Efektin hızı (0 yavaş … 5 hızlı).',
        'h_bright': 'LED parlaklığı.',
        'h_fire': '"Hızlı ateş" atanmış tuşun tıklama aralığı.',
        'h_lang': 'Arayüz dili.',
        'h_color_order': 'Ekrandaki DPI renkleri faredekiyle uyuşmuyorsa bunu değiştir.',
        'h_factory': 'Tüm tuşları Sol/Sağ/Orta tık, Geri/İleri, DPI ve LED düzenine döndürür.',
        'h_undo': 'Uygulamayı açtığındaki ayarlara geri döner.',
        'st_live': 'Değişiklikler anında fareye uygulanır.',
        'st_writing': '● Fareye yazılıyor…', 'st_done': '✓ Fareye uygulandı',
        'st_backup': 'Başlangıç yedeği: {f}', 'st_demo': 'DEMO — gerçek fareye yazılmıyor',
        'lang_detected': 'Dil algılandı: {lang}. Değiştirmek için: Diğer › Dil.',
        'ev_dpi': 'Fare: DPI → kademe {n} ({dpi} DPI)',
        'err_left': 'En az bir tuş "Sol tık" olmalı.',
        'err_one_level': 'En az bir DPI kademesi açık olmalı.',
        'err_active_off': 'Aktif kademe kapatılamaz; önce başka bir kademeyi aktif yap.',
        'err_backup': 'Yedek alınamadı ({e}); fareye hiçbir şey yazılmadı. Kontrol et: {d}',
        'err_verify': 'Doğrulama başarısız: blok {a}. Yedek: {b}',
        'err_notfound': 'SMX-R22 (30fa:1040) bulunamadı. Fare takılı mı?',
        'err_perm': '{p} açılamadı (izin yok). sudo ile çalıştır ya da udev kuralını kur (README).',
        'err_small': 'Pencere çok küçük ({w}x{h}). En az {mw}x{mh} gerekli.',
        'color_title': 'Kademe {n} rengi', 'palette': 'Hazır', 'red': 'Kırmızı', 'green': 'Yeşil', 'blue': 'Mavi',
        'color_help': '↑↓ satır   ←→ değiştir   Enter tamam   Esc vazgeç',
        'list_help': '↑↓ seç   Enter tamam   Esc vazgeç',
        'undone': 'Oturum başındaki ayarlara dönüldü.', 'factory_done': 'Fabrika tuşları uygulandı.',
        'mouse': 'Fare', 'quit_pending': 'Son değişiklik yazılıyor…',
        'custom_sc': 'Kısayol', 'grp_basic': 'Temel işlevler', 'grp_sys': 'Sistem (KDE)', 'grp_edit': 'Düzenleme',
        'grp_web': 'Tarayıcı', 'grp_media': 'Medya', 'grp_custom': 'Özel', 'custom_new': '✎ Özel kısayol oluştur…',
        'builder_title': '{b}: özel kısayol', 'key': 'Tuş',
        'builder_help': '↑↓ satır   ←→ değiştir   Enter kaydet   Esc vazgeç',
        'sc_written': '✓ Fareye yazıldı: {b} → {s}', 'sc_writing': '● Kısayol fareye yazılıyor…',
        'color_hint': '↵ renk', 'preview': 'Önizleme (yaklaşık)', 'pressed': 'Basılan',
        'exp_note': '⚗ = deneysel (fareye göre çalışmayabilir)',
        'led_dpi_hint': 'Not: DPI rengi alttaki ışık şeridine uygulanır; üstteki gösterge ışığının renkleri fareye sabittir.',
        'profile_warn': 'Uyarı: fare profil {n} kullanıyor; bu araç profil 1 tuşlarını düzenler.',
        'wheel_up': 'tekerlek ↑', 'wheel_down': 'tekerlek ↓',
        # CLI
        'cli_levels': 'DPI kademeleri:', 'cli_on': 'açık', 'cli_off': 'kapalı', 'cli_color': 'renk',
        'cli_led': 'LED', 'cli_keys': 'Tuşlar:', 'cli_nochange': 'Değişiklik yok, yazılmadı.',
        'cli_written': 'Yazılan bloklar: {b}', 'cli_backup': 'Yedek: {f}', 'cli_verified': 'Yazıldı ve doğrulandı.',
        'cli_backedup': 'Yedeklendi: {f}', 'cli_same': 'Fare zaten yedekle aynı.', 'cli_restored': 'Geri yüklendi: {b}',
        'cli_valid_dpi': 'Geçerli DPI değerleri: {v}', 'cli_listen': '{s} saniye dinleniyor; fare tuşlarına bas…',
        'error': 'Hata',
    },
    'en': {
        'title': 'SMX-R22 Mouse Control',
        'sec_dpi': 'DPI', 'sec_keys': 'Buttons', 'sec_led': 'Lighting', 'sec_other': 'Other',
        'active_level': 'Active level', 'level': 'Level {n}', 'off': 'Off',
        'mode': 'Mode', 'speed': 'Speed', 'brightness': 'Brightness',
        'fire': 'Rapid fire interval', 'language': 'Language / Dil', 'color_order': 'LED colour mapping', 'inverted': 'inverted',
        'factory_keys': 'Reset buttons to factory', 'undo_all': 'Undo all changes of this session',
        'help_bar': '↑↓ select   ←→ change   Enter colour/list   q quit',
        'h_active': 'The mouse is on this level now. The DPI button on the mouse changes it too.',
        'h_level': '←→ DPI value ("Off" = DPI button skips it)   Enter: change this level\'s colour',
        'h_key': '←→ basic function   Enter: full list incl. shortcuts and media',
        'h_mode': '←→ lighting effect, Enter: pick from list.',
        'h_speed': 'Effect speed (0 slow … 5 fast).',
        'h_bright': 'LED brightness.',
        'h_fire': 'Click interval of a button set to "Rapid fire".',
        'h_lang': 'Interface language.',
        'h_color_order': 'Change this if the DPI colours on screen do not match the mouse.',
        'h_factory': 'Restores Left/Right/Middle click, Back/Forward, DPI and LED buttons.',
        'h_undo': 'Returns to the settings the mouse had when you opened the app.',
        'st_live': 'Changes are applied to the mouse instantly.',
        'st_writing': '● Writing to mouse…', 'st_done': '✓ Applied to mouse',
        'st_backup': 'Startup backup: {f}', 'st_demo': 'DEMO — not writing to a real mouse',
        'lang_detected': 'Language detected: {lang}. Change it under Other › Language.',
        'ev_dpi': 'Mouse: DPI → level {n} ({dpi} DPI)',
        'err_left': 'At least one button must be "Left click".',
        'err_one_level': 'At least one DPI level must be on.',
        'err_active_off': 'The active level cannot be turned off; activate another level first.',
        'err_backup': 'Backup failed ({e}); nothing was written to the mouse. Check: {d}',
        'err_verify': 'Verification failed: block {a}. Backup: {b}',
        'err_notfound': 'SMX-R22 (30fa:1040) not found. Is the mouse plugged in?',
        'err_perm': 'Cannot open {p} (permission denied). Run with sudo or install the udev rule (README).',
        'err_small': 'Window too small ({w}x{h}). Need at least {mw}x{mh}.',
        'color_title': 'Level {n} colour', 'palette': 'Preset', 'red': 'Red', 'green': 'Green', 'blue': 'Blue',
        'color_help': '↑↓ row   ←→ change   Enter OK   Esc cancel',
        'list_help': '↑↓ select   Enter OK   Esc cancel',
        'undone': 'Restored the settings from the start of this session.', 'factory_done': 'Factory buttons applied.',
        'mouse': 'Mouse', 'quit_pending': 'Writing last change…',
        'custom_sc': 'Shortcut', 'grp_basic': 'Basic functions', 'grp_sys': 'System (KDE)', 'grp_edit': 'Editing',
        'grp_web': 'Browser', 'grp_media': 'Media', 'grp_custom': 'Custom', 'custom_new': '✎ Create custom shortcut…',
        'builder_title': '{b}: custom shortcut', 'key': 'Key',
        'builder_help': '↑↓ row   ←→ change   Enter save   Esc cancel',
        'sc_written': '✓ Written to mouse: {b} → {s}', 'sc_writing': '● Writing shortcut to mouse…',
        'color_hint': '↵ colour', 'preview': 'Preview (approximate)', 'pressed': 'Pressed',
        'exp_note': '⚗ = experimental (may not work on every mouse)',
        'led_dpi_hint': 'Note: the DPI colour applies to the bottom LED strip; the top indicator colours are fixed by the mouse.',
        'profile_warn': 'Warning: the mouse uses profile {n}; this tool edits profile 1 buttons.',
        'wheel_up': 'wheel ↑', 'wheel_down': 'wheel ↓',
        'cli_levels': 'DPI levels:', 'cli_on': 'on', 'cli_off': 'off', 'cli_color': 'colour',
        'cli_led': 'LED', 'cli_keys': 'Buttons:', 'cli_nochange': 'No change, nothing written.',
        'cli_written': 'Blocks written: {b}', 'cli_backup': 'Backup: {f}', 'cli_verified': 'Written and verified.',
        'cli_backedup': 'Backed up: {f}', 'cli_same': 'Mouse already matches the backup.', 'cli_restored': 'Restored: {b}',
        'cli_valid_dpi': 'Valid DPI values: {v}', 'cli_listen': 'Listening for {s} s; press mouse buttons…',
        'error': 'Error',
    },
}

LED_MODES = {
    'tr': ['DPI rengi nefes', 'Döngüsel nefes', 'Sabit ışık', 'Akan su (gökkuşağı)', 'Tek renk akış',
           'Kuyruklu yıldız', 'Neon', 'Ambilight', 'Yanıp sönme', 'Star Trek', 'Su dalgası',
           'Renk cümbüşü', 'Tuşa tepki', 'Kapalı'],
    'en': ['DPI breathing', 'Cycle breathing', 'Light on', 'Flowing water', 'Mono water',
           'Comet streak', 'Neon', 'Ambilight', 'Flicker', 'Star Trek', 'Ripple',
           'Enraptured', 'Button response', 'LED off'],
}

FUNC_NAMES = {
    'tr': {0x21: 'Sol tık', 0x23: 'Sağ tık', 0x22: 'Orta tık', 0x24: 'Geri', 0x25: 'İleri',
           0x26: 'DPI döngüsü', 0x2b: 'DPI +', 0x2c: 'DPI −', 0x28: 'Çift tık', 0x29: 'Hızlı ateş',
           0x27: 'Masaüstünü göster', 0x35: 'LED modu döngüsü', 0x00: 'Devre dışı'},
    'en': {0x21: 'Left click', 0x23: 'Right click', 0x22: 'Middle click', 0x24: 'Back', 0x25: 'Forward',
           0x26: 'DPI loop', 0x2b: 'DPI +', 0x2c: 'DPI −', 0x28: 'Double click', 0x29: 'Rapid fire',
           0x27: 'Show desktop', 0x35: 'LED mode loop', 0x00: 'Disabled'},
}

FUNC_KINDS = {
    'tr': {0x0d: 'Klavye kısayolu', 0x0e: 'Klavye kısayolu', 0x0f: 'Medya tuşu', 0x1e: 'Makro', 0x1f: 'Makro',
           0x14: 'Fn', 0x17: 'Profil 1', 0x18: 'Profil 2', 0x19: 'Profil 3', 0x1a: 'Profil 4', None: 'Bilinmeyen'},
    'en': {0x0d: 'Keyboard shortcut', 0x0e: 'Keyboard shortcut', 0x0f: 'Media key', 0x1e: 'Macro', 0x1f: 'Macro',
           0x14: 'Fn', 0x17: 'Profile 1', 0x18: 'Profile 2', 0x19: 'Profile 3', 0x1a: 'Profile 4', None: 'Unknown'},
}

BUTTON_NAMES = {
    'tr': {0: 'Sol tuş', 2: 'Sağ tuş', 1: 'Tekerlek tuşu', 3: 'Yan tuş (arka)', 4: 'Yan tuş (ön)',
           5: 'Üst tuş (DPI)', 7: 'Ek tuş'},
    'en': {0: 'Left button', 2: 'Right button', 1: 'Wheel button', 3: 'Side button (rear)',
           4: 'Side button (front)', 5: 'Top button (DPI)', 7: 'Extra button'},
}

LANG = 'en'
SETTINGS = {}


def T(key, **kw):
    s = S[LANG].get(key) or S['en'][key]
    return s.format(**kw) if kw else s


def _home():
    user = os.environ.get('SUDO_USER')
    return os.path.expanduser(f'~{user}' if user else '~')


def _settings_path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(_home(), '.config')
    return os.path.join(base, 'smx', 'settings.json')


def data_dir():
    base = os.environ.get('XDG_DATA_HOME') or os.path.join(_home(), '.local', 'share')
    return os.path.join(base, 'smx')


def detect():
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
        v = os.environ.get(var, '')
        if v:
            return 'tr' if v.lower().startswith('tr') else 'en'
    return 'en'


def load():
    """Load settings; on first run detect the language and save it. Returns True on first run."""
    global LANG, SETTINGS
    first = False
    try:
        SETTINGS = json.load(open(_settings_path()))
        if SETTINGS.get('lang') not in LANGS:
            raise ValueError
    except (OSError, ValueError):
        SETTINGS = dict(SETTINGS) if isinstance(SETTINGS, dict) else {}
        SETTINGS['lang'] = detect()
        _write()
        first = True
    LANG = SETTINGS['lang']
    if os.environ.get('SMX_LANG') in LANGS:          # temporary override, not saved
        LANG = os.environ['SMX_LANG']
    return first


def set_setting(key, value):
    global LANG
    SETTINGS[key] = value
    if key == 'lang':
        LANG = value
    _write()


def save(lang):
    set_setting('lang', lang)


def _chown(path):
    if os.environ.get('SUDO_UID'):
        try:
            os.chown(path, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
        except OSError:
            pass


def _write():
    path = _settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(SETTINGS, f)
        _chown(path)
        _chown(os.path.dirname(path))
    except OSError:
        pass

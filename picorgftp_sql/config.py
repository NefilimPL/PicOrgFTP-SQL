"""Configuration file loading and persistence."""

from .common import (
    A,
    A6,
    A9,
    AO,
    AF,
    Ar,
    B,
    BT,
    CONFIG_DIR_PROMPT_TITLE,
    DEFAULT_CONFIG,
    E,
    H,
    K,
    M,
    N,
    O,
    P,
    SQL_UPDATE_TEMPLATE,
    AK,
    b,
    c,
    ft,
    k,
    m,
    p,
    r,
    u,
    v,
    w,
)
from .encryption import decrypt, encrypt
from .settings import AC, AM, BASE_DIR_OVERRIDE

CONFIG_PATH = A.path.join(AC, "config.json")
CONFIG_SAVE_FAILED_MSG = "Nie udało się zapisać pliku konfiguracyjnego:\n{error}"


def load_config():
    """Return a configuration dictionary, creating defaults when necessary."""

    # Work on a copy so that callers modifying the result do not mutate
    # DEFAULT_CONFIG, which acts as a template for new installations.
    global CONFIG_PATH
    config_copy = Ar.loads(Ar.dumps(DEFAULT_CONFIG))
    config_path = CONFIG_PATH
    if not A.path.exists(config_path):
        if not BASE_DIR_OVERRIDE:
            chosen_dir = BT.askdirectory(title=CONFIG_DIR_PROMPT_TITLE)
            if chosen_dir:
                config_path = A.path.join(chosen_dir, "config.json")
        if not A.path.exists(config_path):
            # Persist an initial configuration with encrypted secrets so the
            # application can be used immediately after installation.
            initial = {
                H: {
                    v: config_copy[H][v],
                    r: config_copy[H][r],
                    N: encrypt(config_copy[H][N]),
                    M: encrypt(config_copy[H][M]),
                    m: config_copy[H][m],
                },
                P: {
                    c: config_copy[P][c],
                    b: config_copy[P][b],
                    N: encrypt(config_copy[P][N]),
                    M: encrypt(config_copy[P][M]),
                },
                K: {
                    c: config_copy[K][c],
                    b: config_copy[K][b],
                    N: encrypt(config_copy[K][N]),
                    M: encrypt(config_copy[K][M]),
                },
                p: config_copy[p],
                w: config_copy[w],
                ft: config_copy[ft],
                u: config_copy[u],
            }
            try:
                # Ensure the configuration directory exists before writing.
                A.makedirs(A.path.dirname(config_path), exist_ok=True)
                with open(config_path, "w", encoding=k) as handle:
                    Ar.dump(initial, handle, indent=4)
            except E as exc:
                try:
                    with open(AM, "a", encoding=k) as log_file:
                        log_file.write(
                            f"[{A9.now().strftime(A6)}] [USER: {AO}] [PC: {AF}] "
                            f"ERROR: Failed to create config.json: {exc}\n"
                        )
                except Exception:
                    pass
    CONFIG_PATH = config_path
    try:
        with open(CONFIG_PATH, "r", encoding=k) as handle:
            raw_config = Ar.load(handle)
        config_copy[H][v] = raw_config.get(H, {}).get(v, config_copy[H][v])
        config_copy[H][r] = raw_config.get(H, {}).get(r, config_copy[H][r])
        config_copy[H][N] = decrypt(raw_config.get(H, {}).get(N, encrypt(config_copy[H][N])))
        config_copy[H][M] = decrypt(raw_config.get(H, {}).get(M, encrypt(config_copy[H][M])))
        config_copy[H][m] = raw_config.get(H, {}).get(m, config_copy[H][m])
        config_copy[P][c] = raw_config.get(P, {}).get(c, config_copy[P][c])
        config_copy[P][b] = raw_config.get(P, {}).get(b, config_copy[P][b])
        config_copy[P][N] = decrypt(raw_config.get(P, {}).get(N, encrypt(config_copy[P][N])))
        config_copy[P][M] = decrypt(raw_config.get(P, {}).get(M, encrypt(config_copy[P][M])))
        config_copy[K][c] = raw_config.get(K, {}).get(c, config_copy[K][c])
        config_copy[K][b] = raw_config.get(K, {}).get(b, config_copy[K][b])
        config_copy[K][N] = decrypt(raw_config.get(K, {}).get(N, encrypt(config_copy[K][N])))
        config_copy[K][M] = decrypt(raw_config.get(K, {}).get(M, encrypt(config_copy[K][M])))
        config_copy[p] = raw_config.get(p, config_copy[p])
        config_copy[w] = raw_config.get(w, config_copy[w])
        config_copy[ft] = raw_config.get(ft, config_copy[ft])
        config_copy[u] = raw_config.get(u, config_copy[u])
        try:
            # Saving back the normalised structure keeps missing keys aligned
            # with future versions of the configuration schema.
            save_config(config_copy)
        except E:
            pass
    except E as exc:
        try:
            with open(AM, "a", encoding=k) as log_file:
                log_file.write(
                    f"[{A9.now().strftime(A6)}] [USER: {AO}] [PC: {AF}] "
                    f"ERROR: Failed to load config.json: {exc}\n"
                )
        except Exception:
            pass
    return config_copy


def save_config(config):
    """Serialise the provided configuration dictionary to disk."""

    # Persist secrets in encrypted form to avoid storing clear text credentials.
    payload = {
        H: {
            v: config[H][v],
            r: config[H][r],
            N: encrypt(config[H][N]),
            M: encrypt(config[H][M]),
            m: config[H][m],
        },
        P: {
            c: config[P][c],
            b: config[P][b],
            N: encrypt(config[P][N]),
            M: encrypt(config[P][M]),
        },
        K: {
            c: config[K][c],
            b: config[K][b],
            N: encrypt(config[K][N]),
            M: encrypt(config[K][M]),
        },
        p: config.get(p, K),
        w: config.get(w, SQL_UPDATE_TEMPLATE),
        ft: config.get(ft, True),
        u: config.get(u, True),
    }
    try:
        with open(CONFIG_PATH, "w", encoding=k) as handle:
            Ar.dump(payload, handle, indent=4)
    except E as exc:
        O.showerror(AK, CONFIG_SAVE_FAILED_MSG.format(error=exc))
        try:
            with open(AM, "a", encoding=k) as log_file:
                log_file.write(
                    f"[{A9.now().strftime(A6)}] [USER: {AO}] [PC: {AF}] "
                    f"ERROR: Failed to save config.json: {exc}\n"
                )
        except Exception:
            pass


CONFIG = load_config()

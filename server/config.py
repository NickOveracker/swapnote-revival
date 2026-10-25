"""Server configuration (TOML file, Python 3.11+ standard library only).

See server.example.toml for every option and its meaning.
"""
import dataclasses
import fnmatch
import ipaddress
import pathlib
import tomllib


@dataclasses.dataclass
class Config:
    # [server]
    bind: str = '127.0.0.1'
    port: int = 8080
    data: pathlib.Path = pathlib.Path('data')
    server_name: str = ''           # the --server value the patches were built with
    # [access]
    allowed_pids: frozenset = frozenset()       # empty = any console (not recommended)
    allowed_networks: tuple = ()                # empty = any client address
    # [retention]
    delivered_grace_hours: float = 24.0         # delete a note this long after delivery
    max_age_days: float = 30.0                  # delete any note after this long
    # [proxy]
    proxy_enabled: bool = False
    proxy_allow_hosts: tuple = ()
    proxy_username: str = ''
    proxy_password: str = ''
    # [debug]
    log_requests: bool = False                  # store raw requests (incl. notes) in the DB
    verbose: bool = False

    def pid_allowed(self, pid):
        return not self.allowed_pids or pid in self.allowed_pids

    def client_allowed(self, address):
        if not self.allowed_networks:
            return True
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(ip in net for net in self.allowed_networks)

    def is_own_host(self, host):
        name = self.server_name
        host = (host or '').split(':', 1)[0].lower()
        return bool(name) and (host == name or host.endswith('.' + name))

    def proxy_host_allowed(self, host):
        host = (host or '').lower()
        return any(fnmatch.fnmatch(host, pattern) for pattern in self.proxy_allow_hosts)


def load(path):
    raw = tomllib.loads(pathlib.Path(path).read_text())
    server = raw.get('server', {})
    access = raw.get('access', {})
    retention = raw.get('retention', {})
    proxy = raw.get('proxy', {})
    debug = raw.get('debug', {})
    cfg = Config(
        bind=server.get('bind', Config.bind),
        port=int(server.get('port', Config.port)),
        data=pathlib.Path(server.get('data', 'data')),
        server_name=str(server.get('server_name', '')).lower(),
        allowed_pids=frozenset(int(p) for p in access.get('allowed_pids', [])),
        allowed_networks=tuple(ipaddress.ip_network(n, strict=False)
                               for n in access.get('allowed_networks', [])),
        delivered_grace_hours=float(retention.get('delivered_grace_hours', 24)),
        max_age_days=float(retention.get('max_age_days', 30)),
        proxy_enabled=bool(proxy.get('enabled', False)),
        proxy_allow_hosts=tuple(h.lower() for h in proxy.get('allow_hosts', [])),
        proxy_username=str(proxy.get('username', '')),
        proxy_password=str(proxy.get('password', '')),
        log_requests=bool(debug.get('log_requests', False)),
        verbose=bool(debug.get('verbose', False)),
    )
    if not cfg.server_name:
        raise SystemExit('config: [server] server_name is required')
    return cfg

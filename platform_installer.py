#!/usr/bin/env python3
"""
Initializes the FLNet Platform deployment on the current machine.
Requests relevant parameters from the user, generates secrets, and writes
the .env and secret env files needed by the docker-compose deployment.

Leaves the user with instructions on how to then start the platform.
"""
import ipaddress
import re
from typing import Optional
import secrets
import string
import sys
from pathlib import Path

DEFAULT_DOMAIN = "http://localhost"
DEFAULT_NGINX_WEBSERVER_IP = "127.0.0.1"
DEFAULT_NGINX_TCP_IP = "0.0.0.0"
DEFAULT_NGINX_PORT = "8250"
DEFAULT_RELAY_TCP_PORT = "9150"
FLNET_PLATFORM_BASE_DIR = 'FLNET_platform'
DEFAULT_COMPOSE_PROJECT_NAME = 'fl-net-platform'

IMAGE_TAG = "latest"
DEFAULT_MIN_CLIENTS = "3"
DOMAIN_TO_IMAGE = {
    "https://federated-learning.net": f"ghcr.io/fedlearnnet/frontends/global-fl-net:{IMAGE_TAG}",
    "https://daibetes-net.cosy.bio": f"ghcr.io/fedlearnnet/frontends/global-daibetes:{IMAGE_TAG}",
    "https://daibetes-net.federated-learning.net": f"ghcr.io/fedlearnnet/frontends/global-daibetes:{IMAGE_TAG}",
    "https://microb-ai-net.cosy.bio": f"ghcr.io/fedlearnnet/frontends/global-microbaiome:{IMAGE_TAG}",
    "https://microb-ai-net.federated-learning.net": f"ghcr.io/fedlearnnet/frontends/global-microbaiome:{IMAGE_TAG}",
} # Add more domain-to-image mappings here if needed

# fallbacks
DEFAULT_FRONTEND_IMAGE = f"ghcr.io/fedlearnnet/frontends/global-fl-net:{IMAGE_TAG}"

# handling of paths
BASE_DIR_INSTALLER_SCRIPT = Path(__file__).resolve().parent
FLNET_PLATFORM_DIR = BASE_DIR_INSTALLER_SCRIPT / FLNET_PLATFORM_BASE_DIR
FLNET_PLATFORM_BASE_ENV_DIR = 'env'
FLNET_PLATFORM_ENV_DIR = FLNET_PLATFORM_DIR / FLNET_PLATFORM_BASE_ENV_DIR

#TODO: as soon as the docs are deployed we can also link to them in this script!
#
# ============================================================================
# Helper Functions
# ============================================================================
def gen_secret(length: int = 64) -> str:
    """
    Generate a URL-safe random string of given length.
    Uses secrets module for cryptographic randomness.
    """
    # To make sure this works on all systems, we limit to alphanumeric characters
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def write_env_file(filepath: Path, comments: Optional[dict] = None, skip_when_exists: bool = False, **variables) -> bool:
    """
    Write environment variables to a file with overwrite protection.

    Args:
        filepath: Path to the .env file
        comments: Optional dict mapping variable names to comment lines prepended before that variable
        skip_when_exists: If True, skip writing if the file already exists
        **variables: Key-value pairs to write (VAR=value format)

    Returns:
        True if successful, False if user aborted
    """
    if filepath.exists():
        if skip_when_exists:
            print(f"Info: The file '{filepath}' already exists. Skipping.")
            return True
        else:
            print(f"Warning: The file '{filepath}' already exists. Overwriting with new settings.")

    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write variables
    with filepath.open('w') as f:
        for key, value in variables.items():
            if comments and key in comments:
                f.write(f"# {comments[key]}\n")
            f.write(f"{key}={value}\n")

    # Set permissions to 600 (owner read/write only)
    filepath.chmod(0o600)
    return True

class Domain:
    """
    Helper class to parse and validate domain inputs.
    Only https:// is accepted as protocol.
    Parses protocol, domain name and optional port.
    Expects input in the format: https://domain[:port], e.g. 'https://example.com:8443'
    """
    def __init__(self, domain_input: str):
        self._raw_input = domain_input.strip()
        self._protocol = None
        self._domain_name = None
        self._port = None
        self._protocol_is_valid = False
        self._domain_is_valid = False
        self._port_is_valid = True  # default to true if no port specified
        self._parse()

    def _parse(self):
        """Parse the domain input into protocol, domain, and port."""
        domain_input = self._raw_input

        # Protocol is required
        if "://" not in domain_input:
            self._protocol_is_valid = False
            return

        # Extract protocol
        protocol_part, domain_port = domain_input.split("://", 1)
        self._protocol = protocol_part.lower()

        # Validate protocol
        if self._protocol not in ['http', 'https']:
            self._protocol_is_valid = False
            return
        self._protocol_is_valid = True

        # Clean trailing slash
        if domain_port.endswith('/'):
            domain_port = domain_port[:-1]

        # Extract domain and port (if present)
        if ':' in domain_port:
            domain_name, port = domain_port.split(':', 1)
            self._domain_name = domain_name.strip()
            self._port = port.strip()
            if not validate_port(self._port):
                self._port_is_valid = False
                return
        else:
            self._domain_name = domain_port.strip()
            self._port = "80" if self._protocol == "http" else "443"
            self._port_is_valid = True

        # Validate domain
        if len(self._domain_name) > 253:  # Full domain max length
            self._domain_is_valid = False
            return
        if not re.match(r'^[a-zA-Z0-9.-]+$', self._domain_name):
            self._domain_is_valid = False
            return
        if re.match(r'^[-.]|[-.]$', self._domain_name):
            self._domain_is_valid = False
            return
        if '--' in self._domain_name or '..' in self._domain_name:
            self._domain_is_valid = False
            return

        self._domain_is_valid = True

    def protocol(self) -> str | None:
        """Return the protocol (http or https)."""
        return self._protocol

    def domain_name(self) -> str | None:
        """Return the domain name without protocol or port."""
        return self._domain_name

    def port(self) -> str | None:
        """Return the port as string, or None if not specified."""
        return self._port

    def protocol_is_valid(self) -> bool:
        """Check if protocol is valid (http and https are accepted)."""
        return self._protocol_is_valid

    def domain_is_valid(self) -> bool:
        """Check if domain name is valid."""
        return self._domain_is_valid

    def port_is_valid(self) -> bool:
        """Check if port is valid (1-65535)."""
        return self._port_is_valid

    def is_valid(self) -> bool:
        """Check if the entire domain input is valid."""
        return self._protocol_is_valid and self._domain_is_valid and self._port_is_valid

    def is_default_port(self) -> bool:
        """Check if the port is the default (443) for https."""
        if not self.is_valid():
            return False
        if self.protocol() == "https":
            return self._port == "443"
        elif self.protocol() == "http":
            return self._port == "80"
        return False

    def __str__(self) -> str:
        """Return the full domain string with protocol and port."""
        if not self.is_valid():
            return self._raw_input

        if self._port is None:
            if self.protocol() == "https":
                self._port = "443"
            elif self.protocol() == "http":
                self._port = "80"

        # Only show port if it's non-standard (non-443 for https)
        result = f"https://{self._domain_name}"
        if not self.is_default_port():
            result += f":{self._port}"

        return result

def validate_port(port_str: str) -> bool:
    """Validate that port is a number between 1 and 65535."""
    try:
        port = int(port_str)
        return 1 <= port <= 65535
    except ValueError:
        return False

# ============================================================================
# Main Installation Logic
# ============================================================================

def main():
    """Main installation/initialization workflow for the FLNet Platform."""
    print("Starting the initialization of the FLNet Platform deployment...\n")

    # ========================================================================
    # 1. Platform domain configuration
    # vars: domain_obj, deployed_on_domain, hostname
    # ========================================================================
    print("The FLNet Platform must be accessible via a domain name.")
    print("Clients connect to the platform over the network, so a proper domain with HTTPS is required")
    print("to secure those connections.")
    print("The platform's internal nginx listens on a configurable local port. Traffic from your domain")
    print("must reach that port — either directly (if you expose nginx on the right port) or via an")
    print("external reverse proxy (e.g. Apache, Caddy) that you configure separately.\n")

    domain_obj = None
    while True:
        domain_input = input(
            "Enter the domain where the platform will be deployed, including protocol "
            f"(e.g., 'https://federated-learning.example.com'). The default is for only running locally ({DEFAULT_DOMAIN}): "
        ).strip()
        domain_input = domain_input or DEFAULT_DOMAIN

        domain_obj = Domain(domain_input)
        if not domain_obj.protocol_is_valid():
            print("ERROR: Only HTTP and HTTPS are accepted. You must prefix the domain with 'http://' or 'https://'.")
            print("Examples: 'https://federated-learning.example.com', 'http://localhost:8080'")
            continue

        if not domain_obj.domain_is_valid():
            print("ERROR: The domain name is not valid.")
            continue

        if not domain_obj.port_is_valid():
            print(f"ERROR: The port '{domain_obj.port()}' is not valid. Please enter a number between 1 and 65535.")
            continue

        print(f"\nPlatform domain set to: {domain_obj}")
        break

    deployed_on_domain = str(domain_obj)
    hostname = domain_obj.domain_name()
    print()

    # ========================================================================
    # 2. Network port configuration
    # vars: nginx_ip, nginx_port, relay_tcp_port
    # ========================================================================
    print("The platform nginx binds to a specific IP address and port on this machine.")
    if domain_obj.domain_name() != "localhost":
        print("Use 127.0.0.1 (localhost) if an external reverse proxy on this machine will forward traffic.")
        print("Use 0.0.0.0 to expose nginx and therefore the platform directly on all interfaces (e.g. if nginx handles everything).")
    else:
        print("Since the domain is localhost, the platform nginx will bind to localhost only.")

    # NGINX bind IP address
    nginx_ip = None
    while True:
        if domain_obj.domain_name() == "localhost":
            nginx_ip_input = "127.0.0.1"
        else:
            nginx_ip_input = input(
                "Enter the IP address for the platform nginx to bind to. Use 0.0.0.0 to expose on all interfaces, or 127.0.0.1 to bind to localhost only "
            f"(default {DEFAULT_NGINX_WEBSERVER_IP}): "
        ).strip()
        nginx_ip = nginx_ip_input or DEFAULT_NGINX_WEBSERVER_IP
        # Accept localhost as alias for 127.0.0.1
        if nginx_ip == "localhost":
            nginx_ip = "127.0.0.1"
        # Validate: allow 0.0.0.0, 127.0.0.1, or any valid IP
        try:
            ipaddress.ip_address(nginx_ip)
            break
        except ValueError:
            print(f"ERROR: '{nginx_ip}' is not a valid IP address (e.g. 127.0.0.1 or 0.0.0.0).")

    # NGINX local port
    nginx_port = None
    while True:
        nginx_port_input = input(
            f"Enter the port for the platform nginx (default {DEFAULT_NGINX_PORT}): "
        ).strip()
        nginx_port = nginx_port_input or DEFAULT_NGINX_PORT
        if validate_port(nginx_port):
            break
        print(f"ERROR: '{nginx_port}' is not a valid port number (1-65535).")
    print(f"Platform nginx will listen on {nginx_ip}:{nginx_port}.")

    # Relay TCP port
    relay_tcp_port = None
    print("The FLNet Platform deploys a relay server for federated learning.")
    print("The relay server uses a TCP server (and custom elliptic curve encryption).")
    print("You must specify another port for this.")
    print(" This TCP connection is NOT handled via the internal nginx but directly by the relay server container")
    print("The port you give here MUST be reachable from the Clients that connect to this Platform and always runs on the 0.0.0.0 interface.")

    while True:
        relay_tcp_port_input = input(
            f"Enter the TCP port for the relay server endpoint (default {DEFAULT_RELAY_TCP_PORT}): "
        ).strip()
        relay_tcp_port = relay_tcp_port_input or DEFAULT_RELAY_TCP_PORT
        if validate_port(relay_tcp_port):
            break
        print(f"ERROR: '{relay_tcp_port}' is not a valid port number (1-65535).")

    print(f"Relay TCP endpoint will be exposed on 0.0.0.0:{relay_tcp_port}.")
    print()

    # ========================================================================
    # 2b. SSL certificate configuration (optional)
    # vars: fullchain_file, privkey_file, nginx_is_ssl_enabled
    # ========================================================================
    print("Even when usinga reverse Proxy before your FL-Net Platform, you still NEED to provide SSL certificates")
    print("The federated communication channel of the Platform uses TLS using CA-signed certificates.")

    fullchain_file = None
    privkey_file = None
    nginx_is_ssl_enabled = False

    while True:
        fullchain_file_input = input("Enter the path to your SSL certificate file (fullchain.pem)").strip()
        try:
            fullchain_file = Path(fullchain_file_input).absolute()
        except Exception as e:
            print(f"ERROR: Could not resolve the path '{fullchain_file_input}': {e}")
            continue
        break

    while True:
        privkey_file_input = input("Enter the path to your SSL private key file (privkey.pem)").strip()
        try:
            privkey_file = Path(privkey_file_input).absolute()
        except Exception as e:
            print(f"ERROR: Could not resolve the path '{privkey_file_input}': {e}")
            continue
        break

    if nginx_ip == "127.0.0.1":
        while True:
            print("Do you want to use this SSL certificate in your Platform Nginx?")
            print("Select no if you use an external reverse proxy that handles SSL termination and forwards traffic to the Platform Nginx.")
            ssl_enabled_input = input("Do you want to enable SSL for the platform nginx? (y/n, default y): ").strip().lower()

            if ssl_enabled_input in ('y', 'yes', ''):
                nginx_is_ssl_enabled = True
                break
            elif ssl_enabled_input in ('n', 'no'):
                nginx_is_ssl_enabled = False
                break
            else:
                print("Please enter 'y' for yes or 'n' for no.")
    else:
        print("Since the platform nginx is exposed on a non local ip (127.0.0.1), the SSL certificate will be used for the Platform nginx.")
        print("We strongly discourage changing this and do not support changing this as part of this script.")
        nginx_is_ssl_enabled = True

    # success
    print("✓ SSL configuration completed.")
    print()

    # ========================================================================
    # 3. Platform learning configuration
    # vars: min_clients, frontend_image, require authentication
    # ========================================================================
    min_clients = None
    frontend_image = None
    while True:
        min_clients_input = input(
            f"Enter the minimum number of clients required to start a learning process "
            f"(recommended minimum: 3, default {DEFAULT_MIN_CLIENTS}): "
        ).strip()
        min_clients = min_clients_input or DEFAULT_MIN_CLIENTS
        try:
            min_clients_int = int(min_clients)
            if min_clients_int < 1:
                print(f"ERROR: '{min_clients}' is not a valid value. Must be at least 1.")
                continue
            if min_clients_int < 3:
                print(f"WARNING: Setting minimum clients to {min_clients_int} is below the recommended minimum of 3.")
                print("  Privacy-enhancing techniques like SMPC require at least 3 participants.")
                print("  With fewer clients, privacy guarantees may be weakened or unavailable.")
                confirm = input("  Do you want to continue with this lower value? (y/n): ").strip().lower()
                if confirm not in ('y', 'yes'):
                    continue
                print(f"  Continuing with minimum clients set to {min_clients_int} as per user request.")
            break
        except ValueError:
            print(f"ERROR: '{min_clients}' is not a valid integer.")
    print(f"Minimum clients for learning set to {min_clients}.")
    print()
    # Frontend image selection based on domain
    if deployed_on_domain in DOMAIN_TO_IMAGE:
        frontend_image = DOMAIN_TO_IMAGE[deployed_on_domain]
        print(f"Based on the deployment domain, the frontend image is set to: {frontend_image}")
    else:
        print("No specific frontend image configured for the deployment domain.")
        print(f"Using default FLNet frontend image: {DEFAULT_FRONTEND_IMAGE}")
        frontend_image = DEFAULT_FRONTEND_IMAGE

    print("You can require FL-Net Clients connecting to this platform to authenticate via your deployed Keycloak. You have the responsibility to then handle the creation of accounts for Clients to use.")
    print("This also means Clients will loose anonimity.")
    print("We recommend turning authentication on for  as this protects you from unwanted Clients connecting to your platform and acting as malicious Clients.")
    require_authentication = True  # default to requiring authentication
    while True:
        auth_input = input(
            "Do you want to require authentication for FL-Net Clients connecting to this platform? (y/n, default y): "
        ).strip().lower()
        if auth_input in ('y', 'yes', ''):
            require_authentication = True
            break
        elif auth_input in ('n', 'no'):
            require_authentication = False
            break
        else:
            print("Please answer with 'y' or 'n'.")

    # ========================================================================
    # 4. Generate Secrets
    # ========================================================================
    print("Securely generating secrets...\n")
    # All these are written with skip_when_exists=True, so that on a re-run
    # the installer won't overwrite existing secrets
    # and will keep the platform running with the old ones.

    # --- datamodeler-secrets.env ---
    neo4j_password = gen_secret()

    datamodeler_secrets_file = FLNET_PLATFORM_ENV_DIR / 'datamodeler-secrets.env'
    datamodeler_api_client_secret = gen_secret()
    if not write_env_file(
        datamodeler_secrets_file,
        skip_when_exists=True,
        QUARKUS_NEO4J_AUTHENTICATION_PASSWORD=neo4j_password,
        NEO4J_AUTH=f"neo4j/{neo4j_password}",
            # NEO4J_USER is set to 'neo4j' in the docker-compose environment
        QUARKUS_OIDC_CREDENTIALS_SECRET=datamodeler_api_client_secret,
        QUARKUS_KEYCLOAK_ADMIN_CLIENT_CLIENT_SECRET=datamodeler_api_client_secret,
    ):
        sys.exit(1)

    # --- global-learning-secrets.env ---
    global_learning_db_password = gen_secret()
    global_learning_api_client_secret = gen_secret()

    global_learning_secrets_file = FLNET_PLATFORM_ENV_DIR / 'global-learning-secrets.env'
    if not write_env_file(
        global_learning_secrets_file,
        skip_when_exists=True,
        QUARKUS_OIDC_CREDENTIALS_SECRET=global_learning_api_client_secret,
        QUARKUS_KEYCLOAK_ADMIN_CLIENT_CLIENT_SECRET=global_learning_api_client_secret,
        QUARKUS_DATASOURCE_PASSWORD=global_learning_db_password,
        POSTGRES_PASSWORD=global_learning_db_password,
    ):
        sys.exit(1)

    # --- orch-secrets.env ---
    orch_db_password = gen_secret()

    orch_secrets_file = FLNET_PLATFORM_ENV_DIR / 'orch-secrets.env'
    if not write_env_file(
        orch_secrets_file,
        skip_when_exists=True,
        QUARKUS_DATASOURCE_PASSWORD=orch_db_password,
        POSTGRES_PASSWORD=orch_db_password,
    ):
        sys.exit(1)

    # --- keycloak-secrets.env ---
    keycloak_db_password = gen_secret()
    keycloak_bootstrap_admin_password = gen_secret(16)
        # Needs to be used by the admin, so we keep it shorter.
        # We advise the user to change it after first login!
    keycloak_secrets_file = FLNET_PLATFORM_ENV_DIR / 'keycloak-secrets.env'
    if not write_env_file(
        keycloak_secrets_file,
        skip_when_exists=True,
        KC_BOOTSTRAP_ADMIN_USERNAME="admin",
        KC_BOOTSTRAP_ADMIN_PASSWORD=keycloak_bootstrap_admin_password,
        KC_DB_PASSWORD=keycloak_db_password,
        POSTGRES_PASSWORD=keycloak_db_password,
        DATABASE_API_SECRET=global_learning_api_client_secret,
        DATAMODELER_API_SECRET=datamodeler_api_client_secret,
    ):
        sys.exit(1)

    print("All secrets generated and stored securely.\n")
    print()

    # ========================================================================
    # 5. Save the final .env file
    # ========================================================================
    if not write_env_file(
        FLNET_PLATFORM_DIR / '.env',
        skip_when_exists=False,
        IMAGE_TAG=IMAGE_TAG,
        FRONTEND_IMAGE=frontend_image,
        DEPLOYED_ON_DOMAIN=deployed_on_domain,
        HOSTNAME=hostname,
        NGINX_PORT=f"{nginx_ip}:{nginx_port}",
            # nginx bind address. 127.0.0.1 = localhost only (use an external reverse proxy to forward).
            # 0.0.0.0 = exposed on all interfaces (nginx reachable directly from outside).
        EXPOSED_RELAY_TCP_PORT=f"0.0.0.0:{relay_tcp_port}",
        MIN_CLIENTS_NEEDED_FOR_LEARNING=min_clients,
        COMPOSE_PROFILES="ssl" if nginx_is_ssl_enabled else "no-ssl",
        SSL_CERT_PUBLIC_KEY=fullchain_file,
        SSL_CERT_PRIVATE_KEY=privkey_file,
        REQUIRE_CLIENT_AUTHENTICATION="true" if require_authentication else "false",
        COMPOSE_PROJECT_NAME=DEFAULT_COMPOSE_PROJECT_NAME
    ):
        sys.exit(1)

    # ========================================================================
    # 6. Deployment Summary
    # ========================================================================
    print("The FLNet Platform configuration is complete.")
    print("Please follow the instructions of the deployment guide.")
    print("https://federated-learning.net/documentation/docs/deployment/deploy-client")
    if nginx_is_ssl_enabled:
        print("IMPORTANT: The platform nginx is configured to use your provided SSL certificate, make sure in the operation step to consider this on certificate renewal.")
    if nginx_ip == "127.0.0.1":
        print("IMPORTANT: The platform nginx is bound to localhost, make sure you configure a reverse proxy to forward traffic from your domain to the platform nginx.")
        if nginx_is_ssl_enabled:
            print("IMPORTANT: You anyways have SSL termination on the Platform NGINX, make sure your reverse proxy and the Platform NGINX are configured to use the same SSL certificate and private key and that you forward HTTPS traffic to the Platform NGINX.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during installation: {e}", file=sys.stderr)
        sys.exit(1)

import json
import requests
import jwt

from authomatic.providers.oauth2 import OAuth2

import logging
LOGGER = logging.getLogger("PHOENIX")


class CEDAProvider(OAuth2):
    """ CEDA oauth2 provider based on classes within the
    authomatic.providers.oauth2 package.
    """

    user_authorization_url = 'https://slcs.ceda.ac.uk/oauth/authorize'
    access_token_url = 'https://slcs.ceda.ac.uk/oauth/access_token'
    user_info_url = 'https://slcs.ceda.ac.uk/oauth/profile/'
    user_info_scope = ['https://slcs.ceda.ac.uk/oauth/profile/']

    same_origin = False

    type_id = 100000  # Any unused ID will do

    @staticmethod
    def _x_user_parser(user, data):

        user_profile = data.get('profile')
        user.username = user_profile.get('accountid') if user_profile else None
        return user


class KeycloakProvider(OAuth2):
    """ Keycloak oauth2 provider based on classes within the
    authomatic.providers.oauth2 package.
    """

    user_authorization_url = None  # 'http://localhost:8080/auth/realms/demo/protocol/openid-connect/auth'
    access_token_url = None  # 'http://localhost:8080/auth/realms/demo/protocol/openid-connect/token'

    same_origin = False

    type_id = 100000  # Any unused ID will do

    @classmethod
    def _x_credentials_parser(cls, credentials, data):
        LOGGER.debug('data: {}'.format(data))
        return credentials

    @staticmethod
    def _x_user_parser(user, data):
        LOGGER.debug('user data: {}'.format(data))

        if "id_token" not in data:
            LOGGER.warn("ID token not found in login data")
            return

        client_id = "ceda-wps-ui-ceda-ac-uk"
        jwks_uri = (
            "https://accounts.ceda.ac.uk/realms/ceda/protocol/openid-connect/certs"
        )
        issuer = "https://accounts.ceda.ac.uk/realms/ceda"

        jwks = requests.get(jwks_uri, timeout=5).json()["keys"]

        kid_to_key = {
            k["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k)) for k in jwks
        }

        hdr = jwt.get_unverified_header(data["id_token"])
        public_key = kid_to_key[hdr["kid"]]

        claims = jwt.decode(
            data["id_token"],
            key=public_key,
            audience=client_id,
            issuer=issuer,
            algorithms=[hdr["alg"]],
        )

        user.id = claims.get("sid")
        user.name = claims.get("preferred_username")
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.email_verified = claims.get("email_verified")

        return user


def create_keycloak_provider(url, realm):
    return type("MyKeycloakProvider", (KeycloakProvider,), {
        'user_authorization_url': '{}/realms/{}/protocol/openid-connect/auth'.format(url, realm),
        'access_token_url': '{}/realms/{}/protocol/openid-connect/token'.format(url, realm)})

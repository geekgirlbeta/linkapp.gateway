from linkapp.gateway.wsgi import GatewayService
from linkapp.gateway.config import GatewayConfig

config = GatewayConfig()

app = GatewayService(config)
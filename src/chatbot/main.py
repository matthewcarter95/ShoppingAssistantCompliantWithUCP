"""Lambda handler with Mangum adapter."""
from mangum import Mangum
from .app import app

# Create Lambda handler
lambda_handler = Mangum(app, lifespan="off")

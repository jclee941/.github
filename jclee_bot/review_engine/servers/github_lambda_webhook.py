from fastapi import FastAPI
from mangum import Mangum
from starlette.middleware import Middleware
from starlette_context.middleware import RawContextMiddleware

from jclee_bot.review_engine.servers.github_app import router

try:
    from jclee_bot.review_engine.config_loader import apply_secrets_manager_config
    apply_secrets_manager_config()
except Exception as e:
    try:
        from jclee_bot.review_engine.log import get_logger
        get_logger().debug(f"AWS Secrets Manager initialization failed, falling back to environment variables: {e}")
    except Exception:
        # Fail completely silently if log module is not available
        pass

middleware = [Middleware(RawContextMiddleware)]
app = FastAPI(middleware=middleware)
app.include_router(router)

handler = Mangum(app, lifespan="off")


def lambda_handler(event, context):
    return handler(event, context)

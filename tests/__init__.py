import atexit
import logging
import os
import shutil
import warnings


# Suppress noisy test-environment warnings from async mocks and logger handler churn.
warnings.filterwarnings(
    "ignore",
    message="coroutine 'AsyncMockMixin._execute_mock_call' was never awaited",
    category=RuntimeWarning,
)
warnings.filterwarnings(
    "ignore",
    message="unclosed file",
    category=ResourceWarning,
)

# Silence provider bootstrap warnings in tests where API keys are intentionally absent.
logging.getLogger("modules.chat").setLevel(logging.ERROR)


def _cleanup_test_artifacts():
    if os.path.isdir(".angelica"):
        shutil.rmtree(".angelica", ignore_errors=True)


atexit.register(_cleanup_test_artifacts)

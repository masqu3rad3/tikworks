import re
import sys
from pytest import main
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
<<<<<<< HEAD
    sys.exit(main(["./tests/integration"]))
=======
    sys.exit(main(["./tests/integration"]))
>>>>>>> TW-4-deformer-and-weights-workflows

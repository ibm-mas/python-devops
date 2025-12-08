.PHONY: install build lint pyinstaller clean

.venv:
	python3 -m venv .venv

clean:
	rm -rf .venv

install: .venv
	. .venv/bin/activate && python -m pip install --editable .[dev]

build: .venv
	rm -f README.rst
	. .venv/bin/activate && python -m build

# Note: "make install" needs to be ran once before this target will work, but we
# don't want to set it as a dependency otherwise it unnecessarily slows down
# fast implement/test cycles.  "make install" created an editable install of the
# package which is linked to the files you are editing so there is no need to
# re-install after each change.
unit-test:
	. .venv/bin/activate && pytest test/src/mock

lint: .venv
	rm -f README.rst
	. .venv/bin/activate && flake8 src --count --select=E9,F63,F7,F82 --show-source --statistics && flake8 src --count --exit-zero --max-complexity=10 --max-line-length=200 --statistics

pyinstaller: venv
	rm -f README.rst
	. .venv/bin/activate && pyinstaller src/mas-upgrade --onefile --noconfirm --add-data="src/mas/devops/templates/ibm-mas-tekton.yaml:mas/devops/templates" --add-data="src/mas/devops/templates/subscription.yml.j2:mas/devops/templates/" --add-data="src/mas/devops/templates/pipelinerun-upgrade.yml.j2:mas/devops/templates/"

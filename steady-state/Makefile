deploy:
	rm -rf ./build
	pip install -r requirements.txt
	rm -f build.zip
	mkdir -p build
	cp ./main.py ./build/main.py
	# cp -rf ../modules-venv/lib/python3.9/site-packages/* build
	pip install -r requirements.txt -t ./build
	cd ./build; zip -r ../build.zip .
	aws s3 cp ./build.zip s3://code.dev.firedrill.sh/modules/steady_state/ --acl public-read
	aws lambda update-function-code \
		--function-name  firedrill-steady-state-dev \
		--zip-file fileb://build.zip
docker:
	docker build .
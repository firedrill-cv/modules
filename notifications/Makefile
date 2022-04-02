deploy:
	# Remove the old build every time
	rm -rf ./build
	rm -f build.zip
	mkdir -p build

	# Install dependencies into build folder
	pip install -r requirements.txt -t ./build

	# Copy app files to build folder
	cp ./main.py ./build/main.py

	# Zip the entire folder
	cd ./build; zip -r ../latest.zip .

	# Deploy to S3
	aws s3 cp ./latest.zip s3://code.dev.firedrill.sh/modules/notifications/ --acl public-read

update: deploy
	aws lambda update-function-code \
		--function-name  firedrill-outbound-notifications-dev \
		--zip-file fileb://latest.zip
local:
	./local.sh
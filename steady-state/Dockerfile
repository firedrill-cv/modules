FROM public.ecr.aws/lambda/python:3.8 
# Install Python dependencies
COPY ./requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install -U -r  ${LAMBDA_TASK_ROOT}/requirements.txt
COPY ./main.py ./main.py
CMD ["main.main"]

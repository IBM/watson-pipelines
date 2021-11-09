# Sample 2: Traing AutoAI + evaluate model

In this document you will learn how to:
* create project from gallery
* modify the "Run notebook" node in the pipeline
* modify notebook used by "Run notebook" node

## Step 1: [Import](https://dataplatform.cloud.ibm.com/docs/content/wsj/manage-data/import-project.html?context=wdp&audience=wdp) project from gallery
* Open your dashboard at http://dataplatform.cloud.ibm.com. Go to
  "Projects". You should now see the project form sample 1.
  Click on "New project".
![projects](screenshots/sample2-0-0-projects.png)
* Choose "Create a project form a sample or file".
![project from](screenshots/sample2-0-1-project-from.png)
* You should now see the list of project samples to choose from. Choose
  "Train AutoAI and reference model".
![from gallery](screenshots/sample2-0-2-from-gallery.png)
* Choose the Machine Learning instance for your project. You can also
  modify the name and the description.
![create sample project](screenshots/sample2-0-3-create-sample-project.png)
* Your project is now ready.
![ready](screenshots/sample2-0-4-ready.png)
* Go to "Assets" to verify that the project is non-empty.
![assets](screenshots/sample2-0-8-assets.png)

## Step 2: Modify the run-notebook node
* Scroll down to "Pipelines". You should only see a single entry. Click
  it.
![pipeline](screenshots/sample2-1-0-pipeline.png)
* Pick the "Select winning model" node. In its "Notebook" input, you can
  see "Notebook name" option with value "select-winning-model".
![inspect run-notebook](screenshots/sample2-1-1-inspect-run-notebook.png)
* Scroll down. You can see the list of environmental variables passed to the
  notebook.
![env-vars](screenshots/sample2-1-2-env-vars.png)
* Switch to "Outputs" tab. See the "Output variables" list, which
  contains one entry. These are the outputs that the notebook exposes
  back to the node.
![output-variables](screenshots/sample2-1-3-output-variables.png)
* Go to "Global Objects" and add a new Pipeline Parameter. Choose
  "Double" type. Name it "expected_model_metric".
![pipeline param](screenshots/sample2-1-4-pipeline-param.png)
* Pick that Pipeline Parameter for the new value for environmental
  variables list.
![pick env-var](screenshots/sample2-1-5-pick-env-var.png)
* Add it. Make sure to click Save. You are now ready to edit the
  notebook itself to use your newly-defined Pipeline Parameter.
![add env-var](screenshots/sample2-1-6-add-env-var.png)

## Step 3: Modify the notebook asset
* Go back to your pojects. Click on "select-winning-model" notebook,
  the one that the "Select winning model" node is using.
![notebooks](screenshots/sample2-2-0-notebooks.png)
* You should now see the notebook view. It is not editable right now,
  as no Python environment has been started yet.
![select-winninng-model](screenshots/sample2-2-1-select-winning-model.png)
* Scroll down. You will see that the notebook requests you to pass it
  your API key. This is done for security reasons. Please don't ever
  pass it as an environmental variable nor print it to the standard
  output.
![API key](screenshots/sample2-2-2-api-key.png)
* Scroll down. You will see how the notebook reads the environmental
  variables passed to it by the node.
![env-vars](screenshots/sample2-2-3-env-vars.png)
* Scroll down. You will see the very model selection code.
![select model](screenshots/sample2-2-4-select-model.png)
* Scroll down. You will see how the results are stored by calling
  a method in the WSPipelines client. This call requires your API key,
  which is why it was requested above.
![store_results](screenshots/sample2-2-5-store-results.png)
* Now that you have the basic understanding of the notebook's structure,
  click the Edit icon
![edit](screenshots/sample2-2-6-edit.png)
* Wait for the Python environment to initialize.
![wait](screenshots/sample2-2-7-wait.png)
* You can now edit your notebook.

  Add the code to read your new env-var:
  ```python
  EXPECTED_MODEL_METRIC = float(os.getenv('expected_model_metric'))
  ```
![add env-var](screenshots/sample2-2-8-add-env-var.png)
* Add a condition on the relationship of the selected model's metric and
  your env-var. Simply assert or raise an exception.

  ```python
  if AUTOAI_MODEL_METRIC > REFERENCE_MODEL_METRIC:
      print('Selected AutoAI model')
      selected_model_id = AUTOAI_MODEL_ID
      selected_model = AUTOAI_MODEL
      selected_metric = AUTOAI_MODEL_METRIC
  else:
      print('Selected reference model')
      selected_model_id = REFERENCE_MODEL_ID
      selected_model = REFERENCE_MODEL
      selected_metric = REFERENCE_MODEL_METRIC
  ```
  ```python
  if selected_metric < EXPECTED_MODEL_METRIC:
      raise RuntimeError(f"Selected metric value too low! Expected at least: {EXPECTED_MODEL_METRIC}, but got: {selected_metric}")
  ```
![add condition](screenshots/sample2-2-9-add-condition.png)
* Make sure to also insert your API key
![paste API key](screenshots/sample2-2-10-paste-api-key.png)
* Make sure to click "Save" and "Save version". You will see a green
  communicate on the right side of your screen to confirm your notebook
  is now saved.
![save](screenshots/sample2-2-10b-save.png)
* Paste your API key to the other notebook too. Make sure to "Save" and
  "Save version".
![paste API key in the other notebook too](screenshots/sample2-2-11-paste-api-key-in-other-notebook.png)
* You are now ready to run your pipeline.

## Step 4: Run the pipeline
* Open the pipeline and trigger a Trial Run. Populate "deployment_space"
  parameter with your deployment space and "expected_model_metric" with
  0.8
![run with 0.8](screenshots/sample2-3-0-run-0-8.png)
* Wait for your run to complete. Your notebook will probably fail.
  Go to "Select winning model". You can see the error message of your
  choice in the logs.
![exception raised](screenshots/sample2-3-1-exception-raised.png)
* Trigger another Trial Run. This time, use 0.5 as the value.
![run with 0.5](screenshots/sample2-3-2-run-0-5.png)
* Your run should now complete successfully.
![success](screenshots/sample2-3-success.png)

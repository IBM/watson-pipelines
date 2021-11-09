# Sample 1: Training AutoAI models

In this document you will learn how to:
* create a Watson Studio pipeline from gallery sample
* trigger trial run
* move around Tracking UI
* remove a pipeline parameter
* modify node parameters
* add a pipeline parameter

## Step 1: Create a [sample pipeline from gallery](https://dataplatform.cloud.ibm.com/docs/content/wsj/analyze-data/ml-orchestration-sample.html?context=wdp&audience=wdp)
* Open your dashboard at http://dataplatform.cloud.ibm.com. Note how
  now, the "Projects" card under "Overview" headline contains your
  project and "Deployment spaces" contains your deployment space.
  Click on your sample project.
![enter project](screenshots/sample1-0-0-enter-project.png)
* You should now see your project's dashboard. Click "Add to Project".
![add to project](screenshots/sample1-0-1-add-to-project.png)
* You will see the list of assets that you can add to your project.
  Pick "Pipeline", which stands for Watson Studio Pipelines.
![add pipeline](screenshots/sample1-0-2-add-pipeline.png)
* Choose "Gallery sample" and then selectect te "Orchestration
  an AutoAI experiment" sample. Enter your pipeline name. Click
  "Create" in the bottom-right corner.
![pick gallery sample](screenshots/sample1-0-3-gallery-sample.png)
* Wait for your pipeline to be created.
![wait](screenshots/sample1-0-4-wait.png)
* You should now see Watson Studio Pipelines UI with your sample
  pipeline opened in it.
![canvas](screenshots/sample1-0-5-canvas.png)

## Step 2: Trigger trial run
* Open "Run" dropdown and pick "Trial Run". This will create
  a one-time run, as opposed to runs scheduled to execute periodically.
![trial run](screenshots/sample1-1-0-trial-run.png)
* You should see a window to declare the pipeline parameters of your
  run. Click "Select space" under the "deployment_space" parameter.
![run params](screenshots/sample1-1-1-run-params.png)
* You should see the data source browser. Select "Space" and then your
  deployment space. Confirm with "Choose" in the bottom-right corner.
![select space](screenshots/sample1-1-2-select-space.png)
* You are now back to the pipeline parameters window. Note how
  your deployment space's id is now visible instead of the "Select
  space" button. Proceed with generating the API key by clicking
  the "Generate new API key" button under API key header.
![generate API key](screenshots/sample1-1-3-space-selected.png)
* Enter a name for your API key.
![name API key](screenshots/sample1-1-4-name-apikey.png)
* Now your API key is created. You will be able to reuse it in
  the future runs.

  Click the Eye icon to show your API key. Copy and paste it to
  some safe location so that you won't lose it. It can NOT be shown
  ever again later (but you can generate a new one if you lose it).
![API key created](screenshots/sample1-1-5-apikey-created.png)
* You are now back to the pipeline parameters window. Note how
  the API key is now chosen and the "Run" button in the bottom right
  corner is no longer gray. Click it to execute your run.
![run](screenshots/sample1-1-6-run.png)
* Wait for your run to be created.
![wait](screenshots/sample1-1-7-wait.png)
* After your run is created, you will see the execution tracking UI,
  where you can observe your pipeline run being executed.
![tracking](screenshots/sample1-1-8-tracking.png)

## Step 3: Move around Tracking UI
* You are now in the Tracking UI. On the left, under your pipeline's
  name, you can see the status of the whole pipeline run (here:
  running) as well as the number of nodes with given statuses (below).
![statuses](screenshots/sample1-2-0-statuses.png)
* On the right, you can see the Node Inspector with "Click on a node
  to see more details". After double-clicking "Create data file" node,
  you will see some information about it, such as its name, icon and
  component name. You will also see its logs being produced as it
  runs.
![node inspector](screenshots/sample1-2-1a-node-inspector.png)
* Wait until the node changes its status to "Completed" (the green bar
  and tick symbol). You can now see the node status
  summary changed to either "1 Completed, 1 Running, 2 Queued"
  or "2 Completed, 1 Running, 1 Queued". Node that each number
  corresponds to the number of nodes.
![statuses changing](screenshots/sample1-2-1b-statuses-changing.png)
* In the Node Inspector, click "Input/Output". You will now see
  the values of inputs and outputs of the "Create data file" node.
  Scroll down to see them all.
![input-output](screenshots/sample1-2-2-input-output.png)
* Now choose a node which is currently running (the blue bar and
  waiting symbol), it will probably be either "Create AutoAI
  experiment" or "Run AutoAI experiment". Scroll down to see the
  outputs. You can see how, contrary to a Completed "Create data
  file", a running node has "Value unavailable" in the place its
  output values will later appear.
![value unavailable](screenshots/sample1-2-3-value-unavailable.png)
* You can widen or hide the Node Inspector by using the buttons
  in its top-right corner.
![widen inspector](screenshots/sample1-2-4-widen-inspector.png)
![hide inspector](screenshots/sample1-2-5-hide-inspector.png)
* Wait until all of the nodes are Completed. Now, the pipeline status
  changed from Running to Completed. You can see a path to your
  deployment by inspecting the outputs of "Create webservice".
  Note how it points at a deployment in your deployment space.
![completed](screenshots/sample1-2-6-completed.png)

## Step 4: Remove a pipeline parameter
* Return to your pipeline-building UI by clicking the link in the top.
![return](screenshots/sample1-3-0-return.png)
* Click on the Global Objects icon, between the Comments and Settings.
![global objects](screenshots/sample1-3-1-global-objects.png)
* You should now see the Global Objects windows, showing Pipeline
  Parameters. There is currently only one Pipeline Parameter,
  "deployment_space", currently used by two nodes. In the next few
  steps, you will remove the references to it and then remove the
  parameter itself.

  Click the Edit icon to try to modify it.
![pipeline parameters](screenshots/sample1-3-2-pipeline-parameters.png)
* You should now see the "deployment_space" Pipeline Parameter
  modification window. A part of it, however, is grayed-out and
  a you can see an info bar: "Unable to modify type - This pipeline
  parameter is currently being used in 2 nodes".

  Close with "Cancel" and then close the previous window
  with "Return to canvas".
![try modify](screenshots/sample1-3-3-try-modify.png)
* Choose "Create AutoAI experiment" node. Open the Source drop-down
  menu near "Scope" input, pick "Select resource".
![pick scope](screenshots/sample1-3-4-pick-scope.png)
* You can now see the "Select Scope" box. Click it.
![select scope](screenshots/sample1-3-5-select-scope.png)
* You should now see the "Select data source" window. This time,
  both Projects and Spaces are visible, as both projects and spaces
  are allowed as a scope for the "Scope" input of "Create AutoAI
  experiment".

  Choose "Spaces" and then your deployment space.
![select data source](screenshots/sample1-3-6-select-data-source.png)
* Note how right now, your deployment space's name is visible
  under "Scope" input.

  Make sure to click "Save". Otherwise your changes to the node will
  be lost.
![save](screenshots/sample1-3-7-save.png)
* Repeat the above steps for the "Path Scope" input
  of the "Create data file" node.

  Make sure to click "Save".
![save](screenshots/sample1-3-8-repeat.png)
* Open the Global Objects window again. Now, the "deployment_space"
  parameter is assigned to no nodes. Try to modify it again.
![no assigned](screenshots/sample1-3-9-no-assigned.png)
* Now, that no nodes refer to the parameter, you can modify it freely.

  Click "Cancel".
![free to modify](screenshots/sample1-3-10-free-to-modify.png)
* Click the Delete icon. Confirm the deletion.
![delete](screenshots/sample1-3-11-delete.png)
* There are currently no Pipeline Params. Click "Return to canvas".
![delete](screenshots/sample1-3-12-no-params.png)
* Execute another Trial Run. This time, you will only see "API key",
  no "deployment_space". Also, your API key is already populated with
  the value you generated for the previous run. Click "Run".
![run](screenshots/sample1-3-13-run.png)
* Wait for your run to complete. It should finish successfully and
  produce another deployment in your deployment space.
![success](screenshots/sample1-3-14-success.png)

## Step 5: Explore modifying the pipeline
* Go back to the pipeline-building UI. Select "Create AutoAI
  experiment". Open the value dropdown for the "Algorithms to include"
  input. You will see a list of possible values to choose from. Pick
  "LogisticRegressionEstimator".
![estimator list](screenshots/sample1-4-0-estimator-list.png)
* There are currently two estimators already chosen:
  "GradientBoostingClassifierEstimator" and "XGBClassfierEstimator".
  You can remove either with the icon on their respective cards.
  Remove the "GradientBoostingClassifierEstimator".

  Click "Add to list" to add the chosen "LogisticRegressionEstimator".
![remove-add](screenshots/sample1-4-1-remove-add.png)
* Now the "GradientBoostingClassifierEstimator" is removed and
  "LogisticRegressionEstimator" is added. The dropdown menu
  selection got reset to "Select the estimator", allowing you
  to choose yet another value to add.
![replaced](screenshots/sample1-4-2-replaced.png)
* Edit the value in the "Training data split radio" input
  by entering 0.5. You will see a warning informing you that the
  minimum value is 0.85.
![min-val](screenshots/sample1-4-3-min-val.png)
* Enter 0.85. The value will be accepted.

  Click "Save".
![ok val](screenshots/sample1-4-3b-ok-val.png)
* Choose the "Run AutoAI experiment" node. Enter a value under
  the optional input "Model name prefix":
  "sample-bank-marketing-model-".

  Click "Save".
![name prefix](screenshots/sample1-4-4-name-prefix.png)
* Choose the "Create web service" node. Note that
  the optional input "New deployment name" is populated with
  a string literal
  "onboarding-bank-marketing-prediction-deployment".
  In the next few steps, you will create a pipeline parameter
  with that default value and assign that parameter to the input.
![new deployment name](screenshots/sample1-4-5-new-deployment-name.png)
* Open the Global Objects menu. Click either of the "Add pipeline
  parameter" buttons.
![global objects](screenshots/sample1-4-6-global-objects.png)
* Enter name. Pick type "String". Paste
  "onboarding-bank-marketing-prediction-deployment"
  as the default value. Click "Add".
![new pipeline param](screenshots/sample1-4-7-new-pipeline-param.png)
* You can now see the pipeline parameter on the list. Return
  to the canvas.
![pipeline param present](screenshots/sample1-4-8-pipeline-param-present.png)
* Open the dropdown next to the "New deployment name". Choose "Assign
  pipeline parameter".
![assign pipeline param](screenshots/sample1-4-9-assign-pipeline-param.png)
* You should only see one value in the dropdown, the name of the
  pipeline parameter that you have just created. Pick it.
![pick pipeline param](screenshots/sample1-4-10-pick-pipeline-param.png)
* Create a Trial Run. Note that you can now see your newly created
  parameter with the default value that you provided.
![run](screenshots/sample1-4-11-run.png)

## Next
Continue to [Sample 2](./sample02.md)

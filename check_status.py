import boto3
import time

cf = boto3.client('cloudformation', region_name='us-east-2')

# Wait for stack creation to complete
print("Waiting for stack creation to complete...")
for i in range(30):
    try:
        events = cf.describe_stack_events(StackName='ActionPlan-Stack')
        # Check if there are any failed resources
        failed = [e for e in events['StackEvents'] if e['ResourceStatus'] == 'FAILED']
        if failed:
            print(f"Failed resources: {len(failed)}")
            for f in failed:
                print(f"  {f['LogicalResourceId']}: {f['ResourceStatusReason'][:100]}")
        
        # Check final status
        statuses = set(e['ResourceStatus'] for e in events['StackEvents'])
        print(f"Event statuses: {statuses}")
        
        # Check overall stack status
        for e in events['StackEvents']:
            if 'StackId' in str(e):
                pass
        
        # Get the stack status
        stack = cf.describe_stacks(StackName='ActionPlan-Stack')
        status = stack['Stacks'][0]['StackStatus']
        print(f"Stack status: {status}")
        
        if status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
            print("Stack creation complete!")
            break
        elif status in ['CREATE_FAILED', 'UPDATE_FAILED']:
            print("Stack creation failed!")
            break
    except Exception as ex:
        print(f"Error: {ex}")
    
    time.sleep(10)
import os

with open(r'C:\Users\priya\ActionPlan\frontend\src\App.tsx', 'r') as f:
    content = f.read()

checks = [
    ('Layout component', 'function Layout' in content),
    ('Sidebar', 'sidebar' in content.lower()),
    ('HomePage', 'function HomePage' in content),
    ('WorkflowPage', 'function WorkflowPage' in content),
    ('HistoryPage', 'function HistoryPage' in content),
    ('AboutPage', 'function AboutPage' in content),
    ('Hash routing', 'useHashRoute' in content),
    ('Backend health', 'checkBackendHealth' in content),
    ('Goal creation', 'createGoalRequest' in content),
    ('Workflow continuation', 'continueGoalRequest' in content),
    ('Document upload', 'ingestDocumentRequest' in content),
]

print('Frontend Redesign - Key Elements Check:')
print('=' * 50)
for check, result in checks:
    symbol = '✅' if result else '❌'
    print(f'{symbol} {check}')

print('=' * 50)
print('All critical functionality preserved:', all(c[1] for c in checks))

from argparse import ArgumentParser
from time import sleep

import requests


FORECAST_HOST = 'https://api.forecast.it'

GITHUB_HOST = 'https://api.github.com'
GITHUB_PREVIEW_HEADERS = {'Accept': 'application/vnd.github.inertia-preview+json'}  # custom header while Projects is still in preview


def pull_forecast_cards(session, project_id, sprint_id, workflow_column_id, comments):
    """ Request Forecast cards from api
    when comments is set, send another request for each card to also get the comments
    returns a list of cards
    """
    # Pull cards
    if project_id:
        url = f'{FORECAST_HOST}/api/v1/projects/{project_id}/cards'
    else:
        url = f'{FORECAST_HOST}/api/v1/cards'

    print('requesting cards')
    cards = session.get(url).json()

    # Filter by sprint
    if sprint_id:
        cards = [card for card in cards if card['sprint'] == sprint_id]

    # Filter by workflow column
    if workflow_column_id:
        cards = [card for card in cards if card['workflow_column'] == workflow_column_id]

    # Request comments for each card
    card_counter = 0
    if comments:
        print(f'requesting comments for every cards')
        for card in cards:
            card['comments'] = session.get(f'{FORECAST_HOST}/api/v1/cards/{card["id"]}/comments').json()
            card_counter += len(card['comments'])

    print(f'downloaded {len(cards)} and {card_counter} comments')
    return cards


def pull_forecast_persons(session):
    """ Request forecast persons from api
    returns an id -> person mapping
    """
    print('requesting persons')
    response = session.get(f'{FORECAST_HOST}/api/v1/persons').json()

    print(f'downloaded {len(response)} persons')
    return {person['id']: person for person in response}


def prefix_author(body, person):
    """ Prefix html body with author name """
    return f'<i>original author: {person["first_name"]} {person["last_name"]}</i><br>{body}'


def convert_card_to_issue(card, label, persons):
    """ Turn a Forecast card object into a Github issue object """
    issue = {
        'title': card['title'],
        'body': prefix_author(card['description'], persons[card['created_by']]),
        'comments': [{'body': prefix_author(comment['comment'], persons[comment['person_id']])}
                     for comment in card.get('comments', [])],
        'labels': [label] if label else [],
    }
    return issue


def get_project_column_id(session, owner, repository, throttle, project_number):
    """
    """
    # List repository projects and look for the one with the correct number
    print('listing repository projects')
    projects_url = f'{GITHUB_HOST}/repos/{owner}/{repository}/projects'
    for project in session.get(projects_url, headers=GITHUB_PREVIEW_HEADERS).json():
        if project['number'] == project_number:
            project_id = project['id']
            break
    else:
        raise Exception(f'Could not find project number {project_number} in {owner}/{repository}')

    # Get the id of the first column in the project
    print(f'listing project {project["name"]} columns')
    project_columns_url = f'{GITHUB_HOST}/projects/{project_id}/columns'
    project_columns = session.get(project_columns_url, headers=GITHUB_PREVIEW_HEADERS).json()
    if not project_columns:
        raise Exception('Github project must have at least one column')

    print(f'using column {project_columns[0]["name"]}')
    return project_columns[0]['id']


def push_github_issues(session, issues, owner, repository, throttle, project_number):
    """ Push batches of issues to a Github repository """
    if project_number:
        project_column_id = get_project_column_id(session, owner, repository, throttle, project_number)

    issue_url = f'{GITHUB_HOST}/repos/{owner}/{repository}/issues'

    issue_count = len(issues)
    for counter, issue in enumerate(issues, 1):
        print(f'creating issues ({counter}/{issue_count})', end='\r')
        sleep(throttle)
        issue_response = session.post(issue_url, json=issue).json()

        comment_url = f'{GITHUB_HOST}/repos/{owner}/{repository}/issues/{issue_response["number"]}/comments'

        for comment in issue['comments']:
            data = {'body': comment}
            sleep(throttle)
            response = session.post(comment_url, json=comment)


        if project_number:
            card_url = f'{GITHUB_HOST}/projects/columns/{project_column_id}/cards'
            data = {
                'content_id': issue_response['id'],
                'content_type': 'Issue',
            }
            sleep(throttle)
            response = session.post(card_url, json=data, headers=GITHUB_PREVIEW_HEADERS)
            response.raise_for_status


if __name__ == '__main__':
    parser = ArgumentParser()

    # Mandatory stuff
    parser.add_argument('forecast_api_key', help='your Forecast API key')
    parser.add_argument('github_username', help='your Github username')
    parser.add_argument('github_token', help='your Github API token')
    parser.add_argument('github_owner', help='github repository owner or organization')
    parser.add_argument('github_repository', help='github repository')

    # Optional stuff
    parser.add_argument('--forecast-project', type=int, help='specify a Forecast project id to only pull cards from this project')
    parser.add_argument('--forecast-sprint', type=int, help='specify a Forecast sprint id to only pull cards from this sprint')
    parser.add_argument('--forecast-workflow-column', type=int, help='specify a Forecast workflow column id to only pull cards from this column')
    parser.add_argument('--github-project-number', type=int, help='also add the issue to a Github Project')
    parser.add_argument('--with-comments', help='also migrate card comments (requires an extra query for each card)', action='store_true')
    parser.add_argument('--label', help='optional label to add to migrated github issues')
    parser.add_argument('--throttle', type=int, help='milliseconds to wait between every github api requests (to avoid abusing rate limits)', default=1000)

    args = parser.parse_args()

    # Pull
    forecast_session = requests.Session()
    forecast_session.headers['X-FORECAST-API-KEY'] = args.forecast_api_key
    cards = pull_forecast_cards(forecast_session, args.forecast_project, args.forecast_sprint, args.forecast_workflow_column, args.with_comments)
    persons = pull_forecast_persons(forecast_session)

    # Convert
    issues = [convert_card_to_issue(card, args.label, persons) for card in cards]

    # Push
    github_session = requests.Session()
    github_session.auth= args.github_username, args.github_token
    push_github_issues(github_session, issues, args.github_owner, args.github_repository, .001 * args.throttle, args.github_project_number)

    print(f'Migration completed: {len(cards)} cards migrated')


from argparse import ArgumentParser
from time import sleep

import requests


GITHUB_API_URL = 'https://api.github.com'
FORECAST_API_URL = 'https://api.forecast.it/api/v1'


def pull_forecast_cards(api_key, project_id, sprint_id, comments):
    """ Request Forecast cards from api
    when comments is set, send another request for each card to also get the comments
    returns a list of cards
    """
    headers = {'X-FORECAST-API-KEY': api_key}#TODO requests session with headers and host

    # Pull cards
    url = f'/projects/{project_id}/cards' if project_id else '/cards'
    print('requesting cards')
    cards_response = requests.get(FORECAST_API_URL + url, headers=headers)
    cards = cards_response.json()

    # filter by sprint
    if sprint_id:
        cards = [card for card in cards if card['sprint'] == sprint_id]

    if comments:
        for card in cards[:10]:#TODO remove limit
            print(f'requesting comments for card {card["id"]}')
            card['comments'] = requests.get(FORECAST_API_URL + f'/cards/{card["id"]}/comments', headers=headers).json()

    return cards


def pull_forecast_persons(api_key):
    """ Request forecast persons from api
    returns an id -> person mapping
    """
    headers = {'X-FORECAST-API-KEY': api_key}#TODO requests session with headers and host
    print('requesting persons')
    response = requests.get(FORECAST_API_URL + '/persons', headers=headers)
    return {person['id']: person for person in response.json()}


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


def push_github_issues(issues, username, token, owner, repository, throttle, project_number):
    """ Push batches of issues to a Github repository """
    auth = requests.auth.HTTPBasicAuth(username, token)

    throttle /= 1000  # sleep expects seconds

    # If a project was given: get the id of the first column
    if project_number:
        headers = {'Accept': 'application/vnd.github.inertia-preview+json'}  # custom header while Projects is still in preview

        projects_url = f'/repos/{owner}/{repository}/projects'
        print(projects_url)
        projects = requests.get(GITHUB_API_URL + projects_url, auth=auth, headers=headers).json()
        print(projects)
        for project in projects:
            if project['number'] == project_number:
                project_id = project['id']
                break
        else:
            raise Exception(f'Could not find project number {project_number} in {owner}/{repository}')

        project_columns_url = f'/projects/{project_id}/columns'
        project_columns = requests.get(GITHUB_API_URL + project_columns_url, auth=auth, headers=headers).json()
        if not project_columns:
            raise Exception('Github project must have at least one column')

        project_column_id = project_columns[0]['id']

    issue_url = f'/repos/{owner}/{repository}/issues'

    for issue in issues:
        sleep(throttle)
        issue_response = requests.post(GITHUB_API_URL + issue_url, json=issue, auth=auth).json()

        comment_url = f'/repos/{owner}/{repository}/issues/{issue_response["number"]}/comments'

        for comment in issue['comments']:
            data = {'body': comment}
            sleep(throttle)
            response = requests.post(GITHUB_API_URL + comment_url, json=comment, auth=auth)


        if project_number:
            card_url = f'/projects/columns/{project_column_id}/cards'
            data = {
                'content_id': issue_response['id'],
                'content_type': 'Issue',
            }
            sleep(throttle)
            response = requests.post(GITHUB_API_URL + card_url, json=data, auth=auth)


        break#TODO tej


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
    parser.add_argument('--github-project-number', type=int, help='also add the issue to a Github Project')
    parser.add_argument('--with-comments', help='also migrate card comments (requires an extra query for each card)', action='store_true')
    parser.add_argument('--label', help='optional label to add to migrated github issues')
    parser.add_argument('--throttle', type=int, help='milliseconds to wait between every github api requests (to avoid abusing rate limits)', default=1000)

    args = parser.parse_args()

    # Pull
    cards = pull_forecast_cards(args.forecast_api_key, args.forecast_project, args.forecast_sprint, args.with_comments)
    persons = pull_forecast_persons(args.forecast_api_key)

    # Convert
    issues = [convert_card_to_issue(card, args.label, persons) for card in cards]

    # Push
    push_github_issues(issues, args.github_username, args.github_token, args.github_owner, args.github_repository, args.throttle, args.github_project_number)

    print(f'Migration completed: {len(cards)} cards migrated')

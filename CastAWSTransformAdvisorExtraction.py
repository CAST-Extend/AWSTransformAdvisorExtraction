"""
Created on April 2025
@author: NBI
"""
from pickle import EMPTY_LIST

import requests
from typing import List, Dict, Optional
import logging
import json
import sys
import os
from pathlib import Path
import re
import datetime, time
import argparse
from datetime import datetime, timedelta


class PathManager:
    """Manages cross-platform file paths for the application"""
    
    def __init__(self):
        self.base_dir = os.getcwd()
        
    @property
    def paths(self) -> Dict[str, str]:
        return {
            'log_dir': self.get_path('log'),
            'segmentation_json_file': self.get_path('AmazonQCT_Wave_Advisor_final.1.0.json'),
            'results_dir': self.get_path('results')
        }
        
    def get_path(self, *parts: str) -> str:
        """Creates a platform-independent path"""
        return str(Path(self.base_dir).joinpath(*parts))
        
    def create_directories(self) -> None:
        """Creates all necessary directories"""
        for path_name, path in self.paths.items():
            if path_name not in ['properties_template', 'highlight_automation_jar', 'segmentation_json_file']:
                os.makedirs(path, exist_ok=True)
                
    def get_results_file_path(self, repo_name: str, phase: str, timestamp: int) -> str:
        """Creates the results file path"""
        filename = f"HL.results.{repo_name}.{phase}-transformation.{timestamp}.zip"
        return str(Path(self.paths['results_dir']).joinpath(filename))


class RepoDetails:
    def __init__(self, repo_owner: str, repo_name: str, branch_name: str):
        self.repo_id = repo_owner + r'/' + repo_name
        self.repo_url = 'https://github.com/' + self.repo_id + '.git'
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch_name = branch_name
        self.application_id = None

    def __str__(self) -> str:
        return (f"RepoDetails(repo_id={self.repo_id},"
                f"repo_owner = {self.repo_owner}, "
                f"repo_name = {self.repo_name}, "
                f"repo_url = {self.repo_url}, "
                f"branch_name={self.branch_name}")


class CastApiClient:
    def __init__(self, cast_token: str, cast_url: str, timeout: int = 30):
        self.base_url = cast_url + "/WS2"
        self.timeout = timeout
        self.auth_token = cast_token
        self.headers = {
            'Authorization': f"Bearer {cast_token}",
        }
        self.company_id = None

    def get_company_id(self) -> Optional[int]:
        try:
            response = requests.get(
                f"{self.base_url}/OAuthService/currentCompanyId",
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            self.company_id = response.json()
            if self.company_id is not None:
                logger.info(f'CAST Company Id retrieved = {self.company_id}')
                return self.company_id
            
            logger.error('Company ID not found in the response.')
            return None
            
        except Exception as e:
            logger.error(f"Failed to get company ID: {str(e)}")
            return None

    def create_segmentation(self, segmentation_json_file: str) -> Optional[tuple[int,List]] :

        try:
            files = [
                ('file', (os.path.basename(segmentation_json_file),
                          open(segmentation_json_file, 'rb'),
                          'application/json'))
            ]
            post_application_url = f"{self.base_url}/domains/{self.company_id}/segmentations/upload"

            response = requests.post(
                post_application_url,
                headers=self.headers,
                data={},
                files=files,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()

            if data.get("id"):
                segmentation_id = data.get("id")
                if segmentation_id:
                    logger.info(f'Amazon Q Code Transform Segmentation created in CAST Highlight: {segmentation_id}')
                    list_segments = []
                    segments = data.get("segments", [])
                    for wave in segments:
                        wave_definition = {
                            'wave_id': wave.get("id"),
                            'wave_name': wave.get("name"),
                            'wave_description': wave.get("description"),
                            'wave_reference': wave.get("segmentRef")
                        }
                        list_segments.append(wave_definition)
                    return segmentation_id, list_segments

            logger.error(f"Amazon Q Code Transform Segmentation creation failed.")
            return None

        except Exception as e:
            logger.error(f"Failed to create Amazon Q Code Transform Segmentation: {str(e)}")
            return None

    def compute_segmentation(self, segmentation_id: int) -> Optional[List]:
        try:
            post_application_url = f"{self.base_url}/domains/{self.company_id}/segmentations/{segmentation_id}/compute"
            post_application_data = {}

            response = requests.post(
                post_application_url,
                headers=self.headers,
                data=post_application_data,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            if len(data) > 0:
                logger.info(f'Amazon Q Code Transform Segmentation computed successfully in CAST Highlight: {len(data)} applications in segments.')
                result = {}
                for key, id_value in data.items():
                    if id_value not in result:
                        result[id_value] = []
                    result[id_value].append({'application_id':int(key)})

                return [{'wave_id': int(k), 'List_applications': v} for k, v in result.items()]

            logger.error(f"AWS Transform Segmentation computation failed.")
            return None

        except Exception as e:
            logger.error(f"Failed to compute AWS Transform Segmentation: {str(e)}")
            return None

    def get_application_status(self, application_id: int) -> Optional[tuple[str,str]]:
        try:
            response = requests.get(
                f"{self.base_url}/domains/{self.company_id}/applications/{application_id}/results",
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            if data is not None:
                if len(data) > 0:
                    application_status = data[0].get("status")
                    branch_name = data[0].get("snapshotLabel")

                else:
                    application_status = "not scanned"
                    branch_name = "N/A"
                logger.info(f'Application {application_id} status = {application_status}')
                return application_status, branch_name

            logger.error('Application status not found in the response.')
            return None, None

        except Exception as e:
            logger.error(f"Failed to get application status: {str(e)}")
            return None, None

    def get_application_list(self) -> Optional[List]:
        try:
            response = requests.get(
                f"{self.base_url}/domains/{self.company_id}/applications",
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            applications_list = response.json()
            if len(applications_list) > 0:
                logger.info(f'List of applications retrieved = {len(applications_list)} applications')
                return applications_list

            logger.error('No application retrieved.')
            return []

        except Exception as e:
            logger.error(f"Failed to get applications list: {str(e)}")
            return []

def is_valid_github_url(url: str) -> bool:
    if not url:
        return False

    pattern = r"^https:\/\/github\.com\/[\w\-]+\/[\w\-]+\.git$"
    return re.match(pattern, url) is not None

def init_parse_argument() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Extract the "AWS Transform: Advisor for .Net Applications" recommendations from CAST Highlight')
    parser.add_argument('--cast-token', required=True, help='CAST Highlight token')
    parser.add_argument('--cast-url', required=False, help='CAST Highlight URL - default is https://rpa.casthighlight.com',
                        choices=['https://rpa.casthighlight.com', 'https://cloud.casthighlight.com', 'https://app.casthighlight.com', 'https://demo.casthighlight.com'])
    return parser

def write_to_file(file_path, content, erase_content=False):
    """Write end results to a provided file."""
    if erase_content:
        open(file_path, 'w').close()
    fp = open(file_path, 'a')
    fp.write(content)
    fp.close()
    return


if __name__ == "__main__":
    # Parse arguments
    parser = init_parse_argument()
    args = parser.parse_args()

    if args.cast_url is None :
        args.cast_url = "https://rpa.casthighlight.com"

    current_date = datetime.today()
    
    # Initialize path manager
    path_manager = PathManager()
    path_manager.create_directories()
    
    # Setup logging
    log_file = os.path.join(path_manager.paths['log_dir'], 
                           f'CASTAWSTransformAdvisorExtraction_{current_date.strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s] - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, mode="w")
        ]
    )
    
    global logger
    logger = logging.getLogger(__name__)

    # Log parameters
    logger.info('****************** Parameters ******************')
    logger.info(f'Log file Path = {log_file}')
    logger.info(f'Results Directory = {path_manager.paths["results_dir"]}')
    logger.info('************************************************')

    try:
        # Initialize CAST API client
        cast_api = CastApiClient(args.cast_token, args.cast_url)
        company_id = cast_api.get_company_id()
        if not company_id:
            raise ValueError("Failed to get company ID")

        # Create or update the AWS Transform Advisor in CAST Highlight - it returns the list of segments\waves
        segmentation_id, list_segments = cast_api.create_segmentation(path_manager.paths['segmentation_json_file'])

        # Get the list of applications with their repo details
        applications_list = cast_api.get_application_list()
        repo_details_list = []
        for application in applications_list:
            #if "clientRef" in application:
                #if is_valid_github_url(application["clientRef"]):
            application_status, branch_name = cast_api.get_application_status(application["id"])
            if application_status == 'complete':
                if "/" in application["name"]:
                    repo_owner, repo_name = application["name"].split("/",1)
                else:
                    repo_owner = "Unknown"
                    repo_name = application["name"]
                repo = RepoDetails(repo_owner,repo_name,branch_name)
                repo.application_id = application["id"]
                repo_details_list.append(repo)
                logger.info(f'Application {application["id"]} - {application["name"]} retrieved.')


        #Compute the AWS Transform Advisor in CAST Highlight - it returns the list of applications in each segment\wave
        wave_app_list = cast_api.compute_segmentation(segmentation_id)
        wave_app_list = sorted(wave_app_list, key=lambda x: x["wave_id"])

        #Prepare the JSON output
        list_segments = {item["wave_id"]: item for item in list_segments}
        # Merge based on matching 'wave_id'
        for entry in wave_app_list:
            match = list_segments.get(entry["wave_id"])
            if match:
                # Don't overwrite the 'wave_id' field
                entry.update({k: v for k, v in match.items() if k != "wave_id"})

        repo_details_list_dict = [obj.__dict__ for obj in repo_details_list]
        repo_detail_lookup = {repo['application_id']: repo for repo in repo_details_list_dict}

        # Merge segments information with application/repo information
        for wave in wave_app_list:
            for app in wave['List_applications']:
                app_id = app['application_id']
                if app_id in repo_detail_lookup:
                    app.update(repo_detail_lookup[app_id])  # Merge app details into wave_app_list

        # Attribute to check
        required_attribute = "repo_id"

        # Filter out items with missing required attributes
        # keep only applications with repo details
        for wave in wave_app_list:
            wave["List_applications"][:] = [item for item in  wave["List_applications"] if required_attribute in item]

        full_json_file = os.path.join(path_manager.paths['results_dir'],
                                f'FullCASTAWSTransformAdvisorExtraction_{current_date.strftime("%Y%m%d_%H%M%S")}.json')

        # Generate a JSON file with all the segments/waves
        write_to_file(full_json_file, json.dumps(wave_app_list, indent=4))

        for wave in wave_app_list:
            repository_mapping_data = {
                "version": "1.0",
                "repositories": []
            }
            for application in wave["List_applications"]:
                repository_mapping_data["repositories"].extend([{"owner": application["repo_owner"],
                                                                 "name":  application["repo_name"],
                                                                 "sourceBranch": application["branch_name"] }])

            wave_json_file = os.path.join(path_manager.paths['results_dir'],
                                          f'CAST{wave["wave_reference"]}_{current_date.strftime("%Y%m%d_%H%M%S")}.json')
            write_to_file(wave_json_file, json.dumps(repository_mapping_data, indent=4))

    except Exception as e:
        logger.error(f"Script failed: {str(e)}")
        sys.exit(1)
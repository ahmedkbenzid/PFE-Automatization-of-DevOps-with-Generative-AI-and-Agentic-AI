# Docker Agent Dataset Sources

This folder contains normalized dataset pages used by the Docker agent retrieval layer.

## External sources

1. Kaggle Stanford Dockerfiles dataset
- URL: https://www.kaggle.com/datasets/stanfordcompute/dockerfiles
- Notes: Metadata captured from the public page. The page references the public upstream mirror:
  - https://github.com/vsoch/dockerfiles
  - https://github.com/vsoch/dockerfiles/archive/1.0.0.zip

2. Zenodo record (ICSE 2020 Docker artifact)
- URL: https://zenodo.org/records/3628771
- API metadata snapshot stored in: `zenodo_3628771.json`
- Artifact file (from API metadata): `binnacle-icse2020-1.0.0.zip`

3. MSR18 Docker dataset repository list
- URL: https://raw.githubusercontent.com/sealuzh/msr18-docker-dataset/master/dockerfiles.csv
- Local raw copy: `dockerfiles.csv`
- Current row count at ingestion time: 440033

## Normalized knowledge pages

- `pages/dataset-kaggle-dockerfiles.json`
- `pages/dataset-zenodo-3628771.json`
- `pages/dataset-msr18-dockerfiles-repos.json`
- `pages/example-nodejs-multi-stage.json`
- `pages/dataset-msr18-extracted-dockerfiles-sample.json`

Page index file (official PageIndex tree format):
- `page_index.json`

Compatibility catalog (legacy flat list format used by previous local retrievers):
- `page_catalog.json`

## Extracted real-world sample

A small extraction run was performed against the first 20 repository URLs from
`dockerfiles.csv` using the public GitHub API (unauthenticated), resulting in:

- 6 Dockerfiles captured as excerpts
- Stored in `pages/dataset-msr18-extracted-dockerfiles-sample.json`

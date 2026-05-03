# Steps for Publishing to GitHub

This file describes the recommended process for turning this folder into a clean, readable public repository.

## 1. Prepare the GitHub folder contents

Only include publicly shareable materials:
- the final `.atbx` toolbox
- standalone source scripts `Execution.py` and `Validation.py`
- short descriptive texts about the thesis
- screenshots and example maps
- small sample data

Do **not** include:
- internal or sensitive data
- unnecessary old backups
- large exports that are not essential
- local helper files from ArcGIS Pro

## 2. Copy main content to the correct folders

Follow this mapping:
- `toolbox/` — final `.atbx` file
- `src/` — `Execution.py` and `Validation.py`
- `examples/screenshots/` — PNG or JPG map screenshots
- `examples/maps/` — PDF or other map exports
- `sample-data/` — demonstration data

## 3. Fill in the documentation

Before the first commit, edit at least these files:
- `README.md`
- `docs/thesis-summary.md`
- `toolbox/README.md`
- `src/README.md`
- `sample-data/README.md`

## 4. Review what will be public

Before uploading, go through the contents and verify:
- no personal or non-public data is included
- no unnecessarily large files are present
- README explains the difference between `.atbx` and standalone scripts
- sample data can be legally distributed

## 5. Create the repository on GitHub

On GitHub:
1. Click `New repository`.
2. Enter the repository name.
3. Choose `Private` if you want to review everything first.
4. After review, you can switch it to `Public`.

## 6. Initialize Git locally

In the `TOOLBOX/GitHub` folder, open a terminal and run:

```powershell
git init
git add .
git commit -m "Initial repository structure for master's thesis"
```

## 7. Connect the GitHub remote

Replace the URL with your own:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
git branch -M main
git push -u origin main
```

## 8. Review after the first push

On the GitHub website, check:
- that `README.md` renders correctly
- that no unwanted files are publicly visible
- that screenshots and maps make sense without additional explanation

## 9. Doporucena prvni verejna verze

Jako prvni verejnou verzi doporucuji zverejnit:
- `.atbx` toolbox
- `Execution.py`
- `Validation.py`
- kratky popis metodiky
- 2 az 5 screenshotu
- mala cvicna data

## 10. Co muzes doplnit pozdeji

Pozdeji muzes pridat:
- PDF diplomove prace, pokud to chces zverejnit
- detailnejsi dokumentaci metod
- dalsi testovaci data
- release s oznacenou verzi nastroje
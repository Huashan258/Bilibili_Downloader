@echo
git add .

set "year=%date:~0,4%"
set "month=%date:~5,2%"
set "day=%date:~8,2%"
set "formatted_date=%year%-%month%-%day%"

git commit -m "Upload file in %formatted_date%"
git push origin latest -f
pause
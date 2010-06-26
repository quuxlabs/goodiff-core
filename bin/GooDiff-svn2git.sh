#!/bin/sh
#initial git clone
#git svn clone file:///home/goodiff/goodiffng/svnbis/repos/GooDiff/
cd text
cd GooDiff
git svn rebase 
# git bundle creation
git bundle create GooDiff-gitbundle-`date +%F` master
cp GooDiff-gitbundle* /home/adulau/website/foo/goodiff/bundle/

#git svn clone file:///home/goodiff/goodiffng/svnrepos/source source
cd ../..
cd source
git svn rebase
git bundle create GooDiff-gitbundle-rawpages-`date +%F` master
cp GooDiff-gitbundle* /home/adulau/website/foo/goodiff/bundle/


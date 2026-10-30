# If you have ripgrep (rg)
rg -n --hidden -g '!*vendor/*' \
  -e 'namespace Drupal\\' \
  -e 'Magento\\Framework' \
  -e 'Joomla\\CMS' \
  ~/ ~/projects /opt /srv 2>/dev/null

# Plain grep fallbacks (slower)
grep -RIn --exclude-dir=vendor --exclude-dir=node_modules \
  -e 'namespace Drupal\\' -e 'Magento\\Framework' -e 'Joomla\\CMS' \
  ~/ ~/projects /opt /srv 2>/dev/null

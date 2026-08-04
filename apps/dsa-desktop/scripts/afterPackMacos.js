const path = require('node:path');
const { execFileSync } = require('node:child_process');

exports.default = async function afterPackMacos(context) {
  if (context.electronPlatformName !== 'darwin') {
    return;
  }

  const appPath = path.join(
    context.appOutDir,
    `${context.packager.appInfo.productFilename}.app`
  );
  const auditScript = path.join(__dirname, 'macos-signature-audit.sh');

  execFileSync('bash', [auditScript, 'normalize', appPath], {
    stdio: 'inherit',
  });
};

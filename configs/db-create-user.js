const {readFileSync} = require('fs')
const {URL} = require('url')

const {MONGO_URL_FILE: mongoUrlFilePath} = process.env

if (mongoUrlFilePath === undefined) {
    console.error(`The MONGO_URL_FILE variable is undefined.`)
    process.exit(1)
}

const mongoUrlFile = readFileSync(mongoUrlFilePath, 'utf-8')
const mongoUrl = new URL(mongoUrlFile)
const {username: user, password: pwd, pathname} = mongoUrl
const dbName = pathname.slice(1)

const {ok} = db.createUser({
    user,
    pwd,
    roles: [
        {
            role: 'readWrite',
            db: dbName,
        },
    ],
})

if (ok) {
    console.log(`The database ${dbName} with user '${user}' and password ${pwd} was successfully created.`)
} else {
    console.error(`Something went wrong while creating the user.`)
}

const replicaSetId = 'rs0'

const {ok} = rs.initiate(
    {
        _id: replicaSetId,
        version: 1,
        members: [
            { _id: 0, host: 'mongo0' },
            { _id: 1, host: 'mongo1' },
            { _id: 2, host: 'mongo2' },
        ]
    }
)

if (ok !== 1) {
    console.error(`Failed to initialize ${replicaSetId}`)
}
